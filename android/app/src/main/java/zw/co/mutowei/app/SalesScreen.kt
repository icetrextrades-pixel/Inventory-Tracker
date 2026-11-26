package zw.co.mutowei.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Remove
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
import zw.co.mutowei.app.data.SaleCartLine
import zw.co.mutowei.app.data.Shop
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.time.LocalDate
import java.time.ZoneId
import zw.co.mutowei.app.data.BizzyAuditCatalogue

private val SalesInk = Color(0xFF172235)
private val SalesMuted = Color(0xFF7A8492)
private val SalesGold = Color(0xFFD8B978)
private val SalesNavy = Color(0xFF101B2D)
private fun money(minor: Long) = "$" + (minor / 100) + "." + (minor % 100).toString().padStart(2, '0')

@Composable
fun SalesScreen(shop: Shop, padding: PaddingValues) {
    val context = LocalContext.current
    val dao = remember { DatabaseProvider.get(context).stockDao() }
    val products by dao.observeProducts(shop.id).collectAsState(initial = emptyList())
    val sales by dao.observeSales(shop.id).collectAsState(initial = emptyList())
    val scope = rememberCoroutineScope()
    LaunchedEffect(shop) { if (shop == Shop.BIZZY) BizzyAuditCatalogue.seed(dao) }
    val todayStart = remember { LocalDate.now().atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli() }
    val todaySales = sales.filter { it.createdAt >= todayStart }
    val cashToday = todaySales.filter { it.paymentMethod == "CASH" }.sumOf { it.totalMinor }
    val ecoCashToday = todaySales.filter { it.paymentMethod == "ECOCASH" }.sumOf { it.totalMinor }
    var search by remember(shop.id) { mutableStateOf("") }
    var cart by remember(shop.id) { mutableStateOf<Map<String, Int>>(emptyMap()) }
    var payment by remember { mutableStateOf("CASH") }
    var checkoutOpen by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    val cartProducts = cart.mapNotNull { entry -> products.firstOrNull { it.id == entry.key }?.let { it to entry.value } }
    val total = cartProducts.sumOf { it.first.sellingPriceMinor * it.second }
    val filtered = products.filter { it.name.contains(search, ignoreCase = true) }

    LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Sales", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = SalesInk)
            Text(shop.displayName + " · checkout", fontSize = 13.sp, color = SalesMuted)
        }
        item {
            OutlinedTextField(search, { search = it }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                placeholder = { Text("Find a product") }, leadingIcon = { Icon(Icons.Default.Search, null) }, shape = RoundedCornerShape(13.dp))
        }
        item {
            Surface(color = Color.White, shape = RoundedCornerShape(15.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text("TODAY'S TAKINGS", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = SalesMuted, letterSpacing = 1.1.sp)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Cash", color = SalesMuted, fontSize = 12.sp); Text(money(cashToday), fontWeight = FontWeight.SemiBold, color = SalesInk)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("EcoCash", color = SalesMuted, fontSize = 12.sp); Text(money(ecoCashToday), fontWeight = FontWeight.SemiBold, color = SalesInk)
                    }
                    HorizontalDivider()
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Total received", fontWeight = FontWeight.Bold, color = SalesInk); Text(money(cashToday + ecoCashToday), fontWeight = FontWeight.Bold, color = SalesNavy)
                    }
                }
            }
        }
        item { Text("PRODUCTS", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = SalesMuted, letterSpacing = 1.2.sp) }
        if (filtered.isEmpty()) item { Text("No products found. Add products in Stock first.", color = SalesMuted) }
        else items(filtered, key = { it.id }) { product ->
            val qty = cart[product.id] ?: 0
            val priceSet = product.sellingPriceMinor > 0
            Surface(color = Color.White, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(product.name, fontWeight = FontWeight.SemiBold, color = SalesInk)
                        Text((if (priceSet) money(product.sellingPriceMinor) else "Price not set") + " · " +
                            product.quantityOnHand + " " + product.baseUnit + " available", fontSize = 11.sp, color = SalesMuted)
                    }
                    IconButton(enabled = qty > 0, onClick = { cart = if (qty <= 1) cart - product.id else cart + (product.id to (qty - 1)) }) {
                        Icon(Icons.Default.Remove, "Decrease")
                    }
                    Text(qty.toString(), fontWeight = FontWeight.Bold, color = SalesInk)
                    IconButton(enabled = priceSet && qty < product.quantityOnHand, onClick = { cart = cart + (product.id to (qty + 1)) }) {
                        Icon(Icons.Default.Add, "Add")
                    }
                }
            }
        }
        item {
            Surface(color = SalesNavy, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text("CURRENT SALE", color = SalesGold, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
                    if (cartProducts.isEmpty()) Text("Your basket is empty.", color = Color.White.copy(alpha = .8f), fontSize = 13.sp)
                    cartProducts.forEach { entry ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(entry.first.name + " × " + entry.second, color = Color.White, fontSize = 12.sp)
                            Text(money(entry.first.sellingPriceMinor * entry.second), color = Color.White, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    HorizontalDivider(color = Color.White.copy(alpha = .2f))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("TOTAL", color = SalesGold, fontWeight = FontWeight.Bold)
                        Text(money(total), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 21.sp)
                    }
                    Button(onClick = { checkoutOpen = true }, enabled = cartProducts.isNotEmpty() && !busy,
                        modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = SalesGold, contentColor = SalesNavy),
                        shape = RoundedCornerShape(12.dp)) { Text("Proceed to payment", fontWeight = FontWeight.Bold) }
                }
            }
        }
        if (message != null) item { Text(message!!, color = if (message!!.startsWith("Sale saved")) Color(0xFF267A5B) else Color(0xFFB94A48), fontSize = 12.sp) }
        item { Text("RECENT SALES", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = SalesMuted, letterSpacing = 1.2.sp) }
        if (sales.isEmpty()) item { Text("No sales recorded yet.", color = SalesMuted, fontSize = 12.sp) }
        else items(sales.take(20), key = { it.id }) { sale ->
            Surface(color = Color.White, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (sale.paymentMethod == "CASH") "Cash sale" else "EcoCash sale", fontWeight = FontWeight.SemiBold, color = SalesInk)
                        Text(SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(sale.createdAt)), fontSize = 11.sp, color = SalesMuted)
                    }
                    Text(money(sale.totalMinor), fontWeight = FontWeight.Bold, color = SalesInk)
                }
            }
        }
    }

    if (checkoutOpen) AlertDialog(
        onDismissRequest = { if (!busy) checkoutOpen = false },
        title = { Text("Complete sale", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Amount due: " + money(total), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text("Payment method", fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = payment == "CASH", onClick = { payment = "CASH" }); Text("Cash")
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = payment == "ECOCASH", onClick = { payment = "ECOCASH" }); Text("EcoCash")
                }
                Text("Confirming saves the sale and deducts the sold quantities from stock.", fontSize = 12.sp, color = SalesMuted)
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                busy = true
                scope.launch {
                    try {
                        dao.recordSale(shop.id, payment, cartProducts.map { SaleCartLine(it.first.id, it.second) },
                            UUID.randomUUID().toString(), System.currentTimeMillis())
                        cart = emptyMap()
                        message = "Sale saved successfully."
                        checkoutOpen = false
                    } catch (e: Exception) {
                        message = "Sale not saved: " + (e.message ?: "Stock was not changed.")
                    } finally { busy = false }
                }
            }) { Text(if (busy) "Saving…" else "Confirm sale") }
        },
        dismissButton = { TextButton(enabled = !busy, onClick = { checkoutOpen = false }) { Text("Cancel") } }
    )
}
