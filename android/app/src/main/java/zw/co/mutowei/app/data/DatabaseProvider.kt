package zw.co.mutowei.app.data

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

private val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE products ADD COLUMN quantityOnHand INTEGER NOT NULL DEFAULT 0")
    }
}

private val MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("""
            CREATE TABLE IF NOT EXISTS product_packages (
                id TEXT NOT NULL,
                productId TEXT NOT NULL,
                packageName TEXT NOT NULL,
                unitsPerPackage INTEGER NOT NULL,
                createdAt INTEGER NOT NULL,
                PRIMARY KEY(id)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS index_product_packages_productId ON product_packages(productId)")
    }
}

private val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("""
            CREATE TABLE IF NOT EXISTS sales (
                id TEXT NOT NULL PRIMARY KEY,
                shopId TEXT NOT NULL,
                totalMinor INTEGER NOT NULL,
                paymentMethod TEXT NOT NULL,
                createdAt INTEGER NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sales_shopId ON sales(shopId)")
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sales_createdAt ON sales(createdAt)")
        db.execSQL("""
            CREATE TABLE IF NOT EXISTS sale_lines (
                id TEXT NOT NULL PRIMARY KEY,
                saleId TEXT NOT NULL,
                productId TEXT NOT NULL,
                productName TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unitPriceMinor INTEGER NOT NULL,
                lineTotalMinor INTEGER NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sale_lines_saleId ON sale_lines(saleId)")
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sale_lines_productId ON sale_lines(productId)")
    }
}

object DatabaseProvider {
    @Volatile private var instance: MutoweiDatabase? = null

    fun get(context: Context): MutoweiDatabase =
        instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                MutoweiDatabase::class.java,
                "mutowei-local.db"
            ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
                .build().also { instance = it }
        }
}
