package zw.co.mutowei.app.data

import java.util.UUID

enum class Shop(val id: String, val displayName: String, val shortName: String) {
    BOTTLE_STORE("mutowei-bottle-store", "Mutowei Bottle Store", "Bottle Store"),
    BIZZY("bizzy-tuckshop", "Bizzy Tuckshop", "Bizzy"),
    CHIKOFA("chikofa-tuckshop", "Chikofa Tuckshop", "Chikofa")
}

data class StockPreview(
    val name: String,
    val category: String,
    val quantity: Int,
    val unit: String,
    val lowStockAt: Int,
    val sellingPrice: String
) {
    val isLowStock: Boolean get() = quantity <= lowStockAt
}

/**
 * Temporary visual preview only. Replace with Room-backed repository data
 * before enabling live stock operations.
 */
object PreviewStock {
    val byShop = mapOf(
        Shop.BOTTLE_STORE to listOf(
            StockPreview("Castle Lager", "Beer", 48, "bottles", 12, "$1.00"),
            StockPreview("Zambezi", "Beer", 18, "bottles", 12, "$1.20"),
            StockPreview("Coke 500ml", "Soft drinks", 6, "bottles", 10, "$0.80")
        ),
        Shop.BIZZY to listOf(
            StockPreview("Cream Biscuits", "Groceries", 36, "packets", 10, "$0.50"),
            StockPreview("Fine Salt 1kg", "Groceries", 8, "packets", 10, "$0.75"),
            StockPreview("Castle Quart", "Beer", 24, "bottles", 12, "$1.00")
        ),
        Shop.CHIKOFA to listOf(
            StockPreview("Sugar 1kg", "Groceries", 20, "packets", 8, "$1.50"),
            StockPreview("Cooking Oil 2L", "Groceries", 5, "bottles", 6, "$3.50"),
            StockPreview("Pepsi 500ml", "Soft drinks", 15, "bottles", 8, "$0.75")
        )
    )
}

private data class BizzyAuditItem(
    val name: String,
    val quantity: Int,
    val unit: String,
    val category: String,
    val sellingPriceMinor: Long = 0L
)

/**
 * One-time, idempotent import of the 25 November 2026 Bizzy audit opening list.
 * Unknown selling prices deliberately remain unset rather than being guessed.
 */
object BizzyAuditCatalogue {
    private val items = listOf(
        BizzyAuditItem("Castle", 7, "bottles", "Beer"),
        BizzyAuditItem("Black Label", 9, "bottles", "Beer"),
        BizzyAuditItem("Super", 2, "bottles", "Beer"),
        BizzyAuditItem("Sting", 17, "cans", "Drinks"),
        BizzyAuditItem("Pepsi", 42, "bottles", "Drinks"),
        BizzyAuditItem("Mirinda", 15, "bottles", "Drinks"),
        BizzyAuditItem("Dragon", 12, "cans", "Drinks"),
        BizzyAuditItem("Zambezi can", 1, "cans", "Drinks"),
        BizzyAuditItem("Scud", 54, "units", "General"),
        BizzyAuditItem("Loose", 6, "units", "General"),
        BizzyAuditItem("Bites", 20, "units", "Snacks"),
        BizzyAuditItem("Tanganda", 3, "units", "Groceries"),
        BizzyAuditItem("Blue Band", 32, "units", "Groceries"),
        BizzyAuditItem("Dovi", 7, "units", "Groceries", 100L),
        BizzyAuditItem("Sugar", 9, "packets", "Groceries", 300L),
        BizzyAuditItem("Rice", 10, "packets", "Groceries"),
        BizzyAuditItem("Flour", 5, "packets", "Groceries"),
        BizzyAuditItem("Salt 2kg", 8, "packets", "Groceries"),
        BizzyAuditItem("Salt 1kg", 10, "packets", "Groceries"),
        BizzyAuditItem("Coarse 1kg", 8, "packets", "Groceries"),
        BizzyAuditItem("Cook More", 3, "units", "Groceries"),
        BizzyAuditItem("Gango", 11, "units", "Groceries"),
        BizzyAuditItem("Popped Corn", 17, "packets", "Snacks"),
        BizzyAuditItem("King Kurts", 4, "packets", "Snacks"),
        BizzyAuditItem("Maputi", 28, "packets", "Snacks"),
        BizzyAuditItem("Mint Swts", 40, "pieces", "Sweets"),
        BizzyAuditItem("Rockers", 14, "pieces", "Sweets"),
        BizzyAuditItem("Matches", 108, "boxes", "Household"),
        BizzyAuditItem("Tea Leaves", 5, "units", "Groceries"),
        BizzyAuditItem("Tea Leaves 50g", 1, "packets", "Groceries"),
        BizzyAuditItem("Mint Branson Cigarette", 178, "cigarettes", "Cigarettes"),
        BizzyAuditItem("Rajah", 1, "units", "Groceries"),
        BizzyAuditItem("Pegasus", 162, "cigarettes", "Cigarettes", 5L),
        BizzyAuditItem("Madison", 100, "cigarettes", "Cigarettes"),
        BizzyAuditItem("Everest", 14, "cigarettes", "Cigarettes"),
        BizzyAuditItem("Steri", 3, "units", "General"),
        BizzyAuditItem("Plastic Cover", 2, "pieces", "Stationery"),
        BizzyAuditItem("Graph Book", 10, "books", "Stationery"),
        BizzyAuditItem("Pumber", 62, "units", "General"),
        BizzyAuditItem("Pen", 23, "pieces", "Stationery"),
        BizzyAuditItem("Pan-eeze", 29, "units", "General")
    )

    suspend fun seed(dao: StockDao) {
        val now = System.currentTimeMillis()
        items.forEach { item ->
            val productId = UUID.nameUUIDFromBytes(
                ("bizzy-tuckshop:" + item.name.lowercase()).toByteArray()
            ).toString()
            val movementId = UUID.nameUUIDFromBytes(
                ("bizzy-audit-opening:" + item.name.lowercase()).toByteArray()
            ).toString()
            val product = ProductEntity(
                id = productId,
                shopId = Shop.BIZZY.id,
                name = item.name,
                baseUnit = item.unit,
                category = item.category,
                sellingPriceMinor = item.sellingPriceMinor,
                lowStockThreshold = null,
                quantityOnHand = item.quantity,
                updatedAt = now
            )
            val movement = if (item.quantity > 0) StockMovementEntity(
                id = movementId,
                shopId = Shop.BIZZY.id,
                productId = productId,
                movementType = "OPENING",
                quantityDelta = item.quantity,
                reason = "25 Nov 2026 audit opening balance",
                reference = "BIZZY-AUDIT-2026-11-25",
                createdAt = now
            ) else null
            val queue = if (movement != null) SyncQueueEntity(
                transactionId = movementId,
                shopId = Shop.BIZZY.id,
                operation = "STOCK_MOVEMENT",
                payloadJson = "{\"movementId\":\"" + movementId +
                    "\",\"productId\":\"" + productId +
                    "\",\"delta\":" + item.quantity +
                    ",\"reason\":\"25 Nov 2026 audit opening balance\"}",
                createdAt = now
            ) else null
            dao.seedAuditProduct(product, movement, queue)
        }
    }
}
