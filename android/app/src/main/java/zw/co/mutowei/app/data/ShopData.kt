package zw.co.mutowei.app.data

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
