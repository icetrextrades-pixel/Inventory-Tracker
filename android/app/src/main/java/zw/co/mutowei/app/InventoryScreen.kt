package zw.co.mutowei.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import zw.co.mutowei.app.data.DatabaseProvider
import zw.co.mutowei.app.data.ProductEntity
import zw.co.mutowei.app.data.Shop
import zw.co.mutowei.app.data.StockMovementEntity
import zw.co.mutowei.app.data.SyncQueueEntity
import java.util.UUID

private val StockInk = Color(0xFF172235)
private val StockMuted = Color(0xFF7A8492)
private val StockGold = Color(0xFFD8B978)

@Composable
fun InventoryScreen(shop: Shop, padding: PaddingValues) {
    val context = LocalContext.current
    val dao = remember { DatabaseProvider.get(context).stockDao() }
    val products by dao.observeProducts(shop.id).collectAsState(initial = emptyList())
    val scope = rememberCoroutineScope()
    var search by remember { mutableStateOf("") }
    var showAdd by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val visible = products.filter { it.name.contains(search, ignoreCase = true) }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Stock", fontSize = 25.sp, fontWeight = FontWeight.Bold, color = StockInk)
                Text(shop.displayName + " · saved on this device", fontSize = 13.sp, color = StockMuted)
            }
        }
        item {
            OutlinedTextField(
                value = search, onValueChange = { search = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Search products") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true, shape = RoundedCornerShape(14.dp)
            )
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(products.size.toString(), fontSize = 25.sp, fontWeight = FontWeight.Bold, color = StockInk)
                    Text("LOCAL PRODUCTS", fontSize = 10.sp, color = StockMuted, letterSpacing = 1.sp)
                }
                Button(onClick = { showAdd = true }, colors = ButtonDefaults.buttonColors(containerColor = StockInk), shape = RoundedCornerShape(12.dp)) {
                    Icon(Icons.Default.Add, null); Spacer(Modifier.width(6.dp)); Text("Add product")
                }
            }
        }
        if (visible.isEmpty()) {
            item {
                Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Inventory2, null, tint = StockGold, modifier = Modifier.size(34.dp))
                        Spacer(Modifier.height(10.dp))
                        Text(if (products.isEmpty()) "No products added yet" else "No matching products", fontWeight = FontWeight.SemiBold, color = StockInk)
                        Text("Add your first item to start building this shop's stock list.", color = StockMuted, fontSize = 12.sp)
                    }
                }
            }
        } else {
            items(visible, key = { it.id }) { product ->
                Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Inventory2, null, tint = StockGold, modifier = Modifier.size(28.dp))
                        Column(Modifier.weight(1f).padding(start = 12.dp)) {
                            Text(product.name, fontWeight = FontWeight.SemiBold, color = StockInk)
                            Text("${product.category} · ${product.sellingPriceMinor / 100}. ${(product.sellingPriceMinor % 100).toString().padStart(2, '0')} / ${product.baseUnit}", fontSize = 11.sp, color = StockMuted)
                            Text("On hand: ${product.quantityOnHand}", fontWeight = FontWeight.Bold, color = if (product.lowStockThreshold != null && product.quantityOnHand <= product.lowStockThreshold) Color(0xFFB94A48) else StockInk)
                        }
                        OutlinedButton(onClick = {
                            scope.launch {
                                val now = System.currentTimeMillis()
                                val movementId = UUID.randomUUID().toString()
                                val txId = UUID.randomUUID().toString()
                                dao.recordMovement(
                                    StockMovementEntity(movementId, shop.id, product.id, "RECEIVE", 1, "Quick receive", null, now),
                                    SyncQueueEntity(txId, shop.id, "STOCK_MOVEMENT", """{"movementId":"$movementId","productId":"${product.id}","delta":1}""", now)
                                )
                            }
                        }) { Text("+1") }
                    }
                }
            }
        }
        item {
            Text("Inventory is stored locally on this device. Cloud sync will be connected after the data structure is validated.", fontSize = 11.sp, color = StockMuted)
        }
        if (error != null) item { Text(error!!, color = Color(0xFFB94A48), fontSize = 12.sp) }
    }

    if (showAdd) {
        AddProductDialog(
            onDismiss = { showAdd = false },
            onSave = { name, category, unit, price, threshold, opening ->
                scope.launch {
                    try {
                        val now = System.currentTimeMillis()
                        val id = UUID.randomUUID().toString()
                        dao.insertProduct(ProductEntity(
                            id = id, shopId = shop.id, name = name, baseUnit = unit,
                            category = category, sellingPriceMinor = (price * 100).toLong(),
                            lowStockThreshold = threshold, quantityOnHand = 0, updatedAt = now
                        ))
                        if (opening > 0) {
                            val movementId = UUID.randomUUID().toString()
                            dao.recordMovement(
                                StockMovementEntity(movementId, shop.id, id, "OPENING", opening, "Opening stock", null, now),
                                SyncQueueEntity(UUID.randomUUID().toString(), shop.id, "STOCK_MOVEMENT", """{"movementId":"$movementId","productId":"$id","delta":$opening}""", now)
                            )
                        }
                        showAdd = false
                        error = null
                    } catch (e: Exception) {
                        error = "Could not save product. Check that the name is not already in this shop."
                    }
                }
            }
        )
    }
}

@Composable
private fun AddProductDialog(
    onDismiss: () -> Unit,
    onSave: (String, String, String, Double, Int?, Int) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("Groceries") }
    var unit by remember { mutableStateOf("units") }
    var price by remember { mutableStateOf("") }
    var threshold by remember { mutableStateOf("5") }
    var opening by remember { mutableStateOf("0") }
    val valid = name.isNotBlank() && (price.toDoubleOrNull() ?: 0.0) >= 0.0 &&
        price.toDoubleOrNull() != null && (opening.toIntOrNull() ?: -1) >= 0

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add product", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Product name") }, singleLine = true)
                OutlinedTextField(category, { category = it }, label = { Text("Category") }, singleLine = true)
                OutlinedTextField(unit, { unit = it }, label = { Text("Base unit (e.g. bottles, packets)") }, singleLine = true)
                OutlinedTextField(price, { price = it }, label = { Text("Selling price (USD)") }, singleLine = true)
                OutlinedTextField(threshold, { threshold = it }, label = { Text("Low-stock alert at") }, singleLine = true)
                OutlinedTextField(opening, { opening = it }, label = { Text("Opening quantity") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(enabled = valid, onClick = {
                onSave(name.trim(), category.trim().ifBlank { "General" }, unit.trim().ifBlank { "units" },
                    price.toDouble(), threshold.toIntOrNull(), opening.toInt())
            }) { Text("Save product") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}
