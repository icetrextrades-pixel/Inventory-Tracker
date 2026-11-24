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

@Dao
interface StockDao {
    @Query("SELECT * FROM products WHERE shopId = :shopId AND archived = 0 ORDER BY name COLLATE NOCASE")
    fun observeProducts(shopId: String): Flow<List<ProductEntity>>

    @Query("SELECT * FROM stock_movements WHERE shopId = :shopId ORDER BY createdAt DESC")
    fun observeMovements(shopId: String): Flow<List<StockMovementEntity>>

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertProduct(product: ProductEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertMovement(movement: StockMovementEntity)

    @Query("UPDATE products SET quantityOnHand = quantityOnHand + :delta, updatedAt = :updatedAt WHERE id = :productId")
    suspend fun changeQuantity(productId: String, delta: Int, updatedAt: Long)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun enqueue(operation: SyncQueueEntity)

    @Transaction
    suspend fun recordMovement(movement: StockMovementEntity, queueItem: SyncQueueEntity) {
        changeQuantity(movement.productId, movement.quantityDelta, movement.createdAt)
        insertMovement(movement)
        enqueue(queueItem)
    }
}

@Database(
    entities = [ProductEntity::class, StockMovementEntity::class, SyncQueueEntity::class],
    version = 2,
    exportSchema = false
)
abstract class MutoweiDatabase : RoomDatabase() {
    abstract fun stockDao(): StockDao
}
