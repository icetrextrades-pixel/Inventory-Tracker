package zw.co.mutowei.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.History
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
    val movements by dao.observeMovements(shop.id).collectAsState(initial = emptyList())
    val scope = rememberCoroutineScope()
    var search by remember { mutableStateOf("") }
    var showAdd by remember { mutableStateOf(false) }
    var showHistory by remember { mutableStateOf(false) }
    var selectedProduct by remember { mutableStateOf<ProductEntity?>(null) }
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
                OutlinedButton(onClick = { showHistory = true }) {
                    Icon(Icons.Default.History, null); Spacer(Modifier.width(5.dp)); Text("History")
                }
                Spacer(Modifier.width(8.dp))
                Button(onClick = { showAdd = true }, colors = ButtonDefaults.buttonColors(containerColor = StockInk), shape = RoundedCornerShape(12.dp)) {
                    Icon(Icons.Default.Add, null); Spacer(Modifier.width(5.dp)); Text("Add")
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
                            Text("${product.category} · ${product.sellingPriceMinor / 100}.${(product.sellingPriceMinor % 100).toString().padStart(2, '0')} / ${product.baseUnit}", fontSize = 11.sp, color = StockMuted)
                            Text("On hand: ${product.quantityOnHand}", fontWeight = FontWeight.Bold, color = if (product.lowStockThreshold != null && product.quantityOnHand <= product.lowStockThreshold) Color(0xFFB94A48) else StockInk)
                        }
                        OutlinedButton(onClick = { selectedProduct = product }) { Text("Manage") }
                    }
                }
            }
        }
        item { Text("Changes are saved locally. Cloud sync will be connected after the data structure is validated.", fontSize = 11.sp, color = StockMuted) }
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
                        error = "Could not save product. Check the name and try again."
                    }
                }
            }
        )
    }

    selectedProduct?.let { product ->
        StockActionDialog(
            product = product,
            onDismiss = { selectedProduct = null },
            onSave = { kind, quantity, reason ->
                scope.launch {
                    try {
                        val now = System.currentTimeMillis()
                        val delta = if (kind == "RECEIVE") quantity else -quantity
                        val movementId = UUID.randomUUID().toString()
                        dao.recordMovement(
                            StockMovementEntity(movementId, shop.id, product.id, kind, delta, reason, null, now),
                            SyncQueueEntity(UUID.randomUUID().toString(), shop.id, "STOCK_MOVEMENT", """{"movementId":"$movementId","productId":"${product.id}","delta":$delta,"reason":"$reason"}""", now)
                        )
                        selectedProduct = null
                        error = null
                    } catch (e: Exception) {
                        error = "Stock was not changed. Check the quantity available and try again."
                    }
                }
            }
        )
    }

    if (showHistory) {
        AlertDialog(
            onDismissRequest = { showHistory = false },
            title = { Text("Stock movement history", fontWeight = FontWeight.Bold) },
            text = {
                if (movements.isEmpty()) {
                    Text("No stock movements recorded yet.")
                } else {
                    LazyColumn(modifier = Modifier.heightIn(max = 420.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(movements.take(100), key = { it.id }) { movement ->
                            val productName = products.firstOrNull { it.id == movement.productId }?.name ?: "Product"
                            Column {
                                Text(productName, fontWeight = FontWeight.SemiBold)
                                Text("${movement.movementType} · ${if (movement.quantityDelta > 0) "+" else ""}${movement.quantityDelta} · ${movement.reason ?: "No reason"}", fontSize = 12.sp, color = StockMuted)
                                Text(java.text.SimpleDateFormat("dd MMM yyyy, HH:mm", java.util.Locale.getDefault()).format(java.util.Date(movement.createdAt)), fontSize = 10.sp, color = StockMuted)
                            }
                            Divider()
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showHistory = false }) { Text("Close") } }
        )
    }
}

@Composable
private fun StockActionDialog(
    product: ProductEntity,
    onDismiss: () -> Unit,
    onSave: (String, Int, String) -> Unit
) {
    var kind by remember { mutableStateOf("RECEIVE") }
    var quantity by remember { mutableStateOf("1") }
    var reason by remember { mutableStateOf("") }
    val amount = quantity.toIntOrNull() ?: 0
    val valid = amount > 0 && (kind == "RECEIVE" || amount <= product.quantityOnHand) && reason.isNotBlank()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Manage ${product.name}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Current on hand: ${product.quantityOnHand}", fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = kind == "RECEIVE", onClick = { kind = "RECEIVE" })
                    Text("Receive stock")
                    Spacer(Modifier.width(8.dp))
                    RadioButton(selected = kind == "ADJUSTMENT", onClick = { kind = "ADJUSTMENT" })
                    Text("Remove / adjust")
                }
                OutlinedTextField(quantity, { quantity = it.filter(Char::isDigit) }, label = { Text("Quantity") }, singleLine = true)
                OutlinedTextField(reason, { reason = it }, label = { Text("Reason (required)") }, singleLine = true)
                if (kind == "ADJUSTMENT" && amount > product.quantityOnHand) {
                    Text("Quantity cannot exceed current stock.", color = Color(0xFFB94A48), fontSize = 12.sp)
                }
            }
        },
        confirmButton = {
            TextButton(enabled = valid, onClick = { onSave(kind, amount, reason.trim()) }) { Text("Save movement") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
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
    val parsedPrice = price.toDoubleOrNull()
    val parsedOpening = opening.toIntOrNull()
    val valid = name.isNotBlank() && parsedPrice != null && parsedPrice >= 0.0 &&
        parsedOpening != null && parsedOpening >= 0 && (threshold.isBlank() || (threshold.toIntOrNull() ?: -1) >= 0)

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
                    parsedPrice!!, threshold.toIntOrNull(), parsedOpening!!)
            }) { Text("Save product") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}
