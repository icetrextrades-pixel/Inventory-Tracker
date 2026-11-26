package zw.co.mutowei.app.data

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Entity(
    tableName = "products",
    indices = [Index(value = ["shopId", "name"], unique = true)]
)
data class ProductEntity(
    @PrimaryKey val id: String,
    val shopId: String,
    val name: String,
    val baseUnit: String,
    val category: String,
    val sellingPriceMinor: Long,
    val lowStockThreshold: Int?,
    val quantityOnHand: Int = 0,
    val updatedAt: Long,
    val archived: Boolean = false
)

@Entity(tableName = "product_packages", indices = [Index("productId")])
data class ProductPackageEntity(
    @PrimaryKey val id: String,
    val productId: String,
    val packageName: String,
    val unitsPerPackage: Int,
    val createdAt: Long
)

@Entity(tableName = "stock_movements", indices = [Index("shopId"), Index("productId"), Index("createdAt")])
data class StockMovementEntity(
    @PrimaryKey val id: String,
    val shopId: String,
    val productId: String,
    val movementType: String,
    val quantityDelta: Int,
    val reason: String?,
    val reference: String?,
    val createdAt: Long,
    val syncState: String = "PENDING"
)

@Entity(tableName = "sync_queue", indices = [Index("state"), Index("createdAt")])
data class SyncQueueEntity(
    @PrimaryKey val transactionId: String,
    val shopId: String,
    val operation: String,
    val payloadJson: String,
    val createdAt: Long,
    val state: String = "PENDING",
    val attempts: Int = 0
)


@Entity(tableName = "sales", indices = [Index("shopId"), Index("createdAt")])
data class SaleEntity(
    @PrimaryKey val id: String,
    val shopId: String,
    val totalMinor: Long,
    val paymentMethod: String,
    val createdAt: Long
)

@Entity(tableName = "sale_lines", indices = [Index("saleId"), Index("productId")])
data class SaleLineEntity(
    @PrimaryKey val id: String,
    val saleId: String,
    val productId: String,
    val productName: String,
    val quantity: Int,
    val unitPriceMinor: Long,
    val lineTotalMinor: Long
)

data class SaleCartLine(val productId: String, val quantity: Int)

@Dao
interface StockDao {
    @Query("SELECT * FROM products WHERE id = :productId LIMIT 1")
    suspend fun getProduct(productId: String): ProductEntity?

    @Query("SELECT * FROM sales WHERE shopId = :shopId ORDER BY createdAt DESC LIMIT 100")
    fun observeSales(shopId: String): Flow<List<SaleEntity>>

    @Query("SELECT * FROM sale_lines WHERE saleId = :saleId ORDER BY productName COLLATE NOCASE")
    suspend fun getSaleLines(saleId: String): List<SaleLineEntity>

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertSale(sale: SaleEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertSaleLines(lines: List<SaleLineEntity>)

    @Query("SELECT * FROM products WHERE shopId = :shopId AND archived = 0 ORDER BY name COLLATE NOCASE")
    fun observeProducts(shopId: String): Flow<List<ProductEntity>>

    @Query("SELECT * FROM stock_movements WHERE shopId = :shopId ORDER BY createdAt DESC")
    fun observeMovements(shopId: String): Flow<List<StockMovementEntity>>

    @Query("SELECT * FROM product_packages WHERE productId = :productId ORDER BY packageName COLLATE NOCASE")
    fun observePackages(productId: String): Flow<List<ProductPackageEntity>>

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertPackage(productPackage: ProductPackageEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertProduct(product: ProductEntity)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertProductIfMissing(product: ProductEntity): Long

    @Transaction
    suspend fun seedAuditProduct(
        product: ProductEntity,
        movement: StockMovementEntity?,
        queueItem: SyncQueueEntity?
    ) {
        val insertedRowId = insertProductIfMissing(product)
        if (insertedRowId != -1L && movement != null && queueItem != null) {
            insertMovement(movement)
            enqueue(queueItem)
        }
    }

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertMovement(movement: StockMovementEntity)

    @Query("UPDATE products SET quantityOnHand = quantityOnHand + :delta, updatedAt = :updatedAt WHERE id = :productId AND quantityOnHand + :delta >= 0")
    suspend fun changeQuantity(productId: String, delta: Int, updatedAt: Long): Int

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun enqueue(operation: SyncQueueEntity)

    @Transaction
    suspend fun recordSale(shopId: String, paymentMethod: String, cart: List<SaleCartLine>, saleId: String, createdAt: Long) {
        require(paymentMethod == "CASH" || paymentMethod == "ECOCASH") { "Unsupported payment method" }
        require(cart.isNotEmpty()) { "Cart is empty" }
        require(cart.all { it.quantity > 0 }) { "Invalid sale quantity" }
        require(cart.map { it.productId }.distinct().size == cart.size) { "Duplicate cart item" }
        val products = cart.map { line ->
            val product = getProduct(line.productId) ?: error("Product no longer exists")
            check(product.shopId == shopId && !product.archived) { "Product belongs to another shop" }
            check(product.sellingPriceMinor > 0L) { "Selling price is not set for ${product.name}" }
            check(product.quantityOnHand >= line.quantity) { "Not enough stock for ${product.name}" }
            product to line.quantity
        }
        val total = products.sumOf { (product, qty) -> product.sellingPriceMinor * qty }
        insertSale(SaleEntity(saleId, shopId, total, paymentMethod, createdAt))
        insertSaleLines(products.map { (product, qty) ->
            SaleLineEntity(UUID.randomUUID().toString(), saleId, product.id, product.name, qty,
                product.sellingPriceMinor, product.sellingPriceMinor * qty)
        })
        products.forEach { (product, qty) ->
            val movementId = UUID.randomUUID().toString()
            val delta = -qty
            val updated = changeQuantity(product.id, delta, createdAt)
            check(updated == 1) { "Stock changed during checkout for ${product.name}" }
            insertMovement(StockMovementEntity(movementId, shopId, product.id, "SALE", delta,
                "Sale $saleId", saleId, createdAt))
            enqueue(SyncQueueEntity(UUID.randomUUID().toString(), shopId, "STOCK_MOVEMENT",
                """{"movementId":"$movementId","productId":"${product.id}","delta":$delta,"saleId":"$saleId"}""", createdAt))
        }
        enqueue(SyncQueueEntity(UUID.randomUUID().toString(), shopId, "SALE",
            """{"saleId":"$saleId","totalMinor":$total,"paymentMethod":"$paymentMethod"}""", createdAt))
    }

    @Transaction
    suspend fun recordMovement(movement: StockMovementEntity, queueItem: SyncQueueEntity) {
        val updated = changeQuantity(movement.productId, movement.quantityDelta, movement.createdAt)
        check(updated == 1) { "Stock cannot go below zero or product no longer exists" }
        insertMovement(movement)
        enqueue(queueItem)
    }
}

@Database(
    entities = [ProductEntity::class, ProductPackageEntity::class, StockMovementEntity::class, SyncQueueEntity::class, SaleEntity::class, SaleLineEntity::class],
    version = 4,
    exportSchema = false
)
abstract class MutoweiDatabase : RoomDatabase() {
    abstract fun stockDao(): StockDao
}
