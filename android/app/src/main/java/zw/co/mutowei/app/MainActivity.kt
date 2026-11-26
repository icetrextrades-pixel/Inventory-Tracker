package zw.co.mutowei.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import zw.co.mutowei.app.data.PreviewStock
import zw.co.mutowei.app.data.Shop
import zw.co.mutowei.app.data.StockPreview

private val Navy = Color(0xFF101B2D)
private val NavySoft = Color(0xFF1B2A40)
private val Gold = Color(0xFFD8B978)
private val Canvas = Color(0xFFF5F3EE)
private val Ink = Color(0xFF172235)
private val Muted = Color(0xFF7A8492)
private val Green = Color(0xFF267A5B)
private val Red = Color(0xFFB94A48)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MutoweiTheme { MutoweiApp() } }
    }
}

@Composable
private fun MutoweiTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Navy,
            secondary = Gold,
            background = Canvas,
            surface = Color.White,
            onPrimary = Color.White,
            onBackground = Ink,
            onSurface = Ink
        ),
        content = content
    )
}

private enum class Destination(val label: String) {
    HOME("Home"), STOCK("Stock"), SALES("Sales"), RECORDS("Records"), ACCOUNT("Account")
}

@Composable
private fun MutoweiApp() {
    var destination by remember { mutableStateOf(Destination.HOME) }
    var selectedShop by remember { mutableStateOf(Shop.BIZZY) }
    var search by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("All") }

    Scaffold(
        containerColor = Canvas,
        bottomBar = {
            NavigationBar(containerColor = Color.White, tonalElevation = 10.dp) {
                Destination.entries.forEach { item ->
                    val icon = when (item) {
                        Destination.HOME -> Icons.Default.Home
                        Destination.STOCK -> Icons.Default.Inventory2
                        Destination.SALES -> Icons.Default.PointOfSale
                        Destination.RECORDS -> Icons.Default.ReceiptLong
                        Destination.ACCOUNT -> Icons.Default.AccountCircle
                    }
                    NavigationBarItem(
                        selected = destination == item,
                        onClick = { destination = item },
                        icon = { Icon(icon, contentDescription = item.label) },
                        label = { Text(item.label, fontSize = 10.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Navy,
                            selectedTextColor = Navy,
                            indicatorColor = Gold.copy(alpha = .24f),
                            unselectedIconColor = Muted
                        )
                    )
                }
            }
        }
    ) { padding ->
        when (destination) {
            Destination.HOME -> HomeScreen(selectedShop, { selectedShop = it }, { destination = it }, padding)
            Destination.STOCK -> InventoryScreen(selectedShop, padding)
            Destination.SALES -> SalesScreen(selectedShop, padding)
            Destination.RECORDS -> PlaceholderScreen("Records", "Purchases, stock movements and audit history will live here.", Icons.Default.ReceiptLong, padding)
            Destination.ACCOUNT -> UpdateScreen(padding)
        }
    }
}

@Composable
private fun PageHeader(title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, fontSize = 25.sp, fontWeight = FontWeight.Bold, color = Ink)
        Text(subtitle, fontSize = 13.sp, color = Muted)
    }
}

@Composable
private fun ShopPicker(selected: Shop, onSelect: (Shop) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("ACTIVE SHOP", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Muted, letterSpacing = 1.4.sp)
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Shop.entries.forEach { shop ->
                val active = selected == shop
                Surface(
                    onClick = { onSelect(shop) },
                    shape = RoundedCornerShape(50),
                    color = if (active) Navy else Color.White,
                    border = if (active) null else androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE4E1D9))
                ) {
                    Text(
                        shop.shortName,
                        modifier = Modifier.padding(horizontal = 15.dp, vertical = 10.dp),
                        color = if (active) Gold else Ink,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }
        }
    }
}

@Composable
private fun HomeScreen(
    shop: Shop,
    onShop: (Shop) -> Unit,
    onNavigate: (Destination) -> Unit,
    padding: PaddingValues
) {
    val products = PreviewStock.byShop[shop].orEmpty()
    val low = products.count { it.isLowStock }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 24.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("MUTOWEI INVESTMENTS", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.6.sp)
                    Text("WhatKind?", color = Navy, fontSize = 28.sp, fontWeight = FontWeight.ExtraBold)
                }
                Surface(color = Navy, shape = CircleShape) {
                    Icon(Icons.Default.NotificationsNone, null, tint = Gold, modifier = Modifier.padding(12.dp))
                }
            }
        }
        item { PageHeader("Good day.", shop.displayName) }
        item { ShopPicker(shop, onShop) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricCard("PRODUCTS", products.size.toString(), Icons.Default.Inventory2, Modifier.weight(1f))
                MetricCard("LOW STOCK", low.toString(), Icons.Default.WarningAmber, Modifier.weight(1f), alert = low > 0)
            }
        }
        item {
            Surface(shape = RoundedCornerShape(22.dp), color = Navy, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("STOCK CONTROL", color = Gold, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp)
                    Text("Know what you have.\nKnow what moves.", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Text("Track deliveries, adjustments and every stock movement.", color = Color(0xFFCFD5DF), fontSize = 12.sp)
                    Button(
                        onClick = { onNavigate(Destination.STOCK) },
                        colors = ButtonDefaults.buttonColors(containerColor = Gold, contentColor = Navy),
                        shape = RoundedCornerShape(12.dp)
                    ) { Text("Open stock", fontWeight = FontWeight.Bold); Icon(Icons.Default.ArrowForward, null, modifier = Modifier.padding(start = 8.dp)) }
                }
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("Stock to watch", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Ink)
                Spacer(Modifier.weight(1f))
                Text("View all", color = Green, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clickable { onNavigate(Destination.STOCK) })
            }
        }
        items(products.filter { it.isLowStock }) { ProductRow(it) }
        item {
            Text("PREVIEW BUILD · SAMPLE STOCK ONLY", color = Muted, fontSize = 9.sp, letterSpacing = 1.sp)
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, icon: androidx.compose.ui.graphics.vector.ImageVector, modifier: Modifier, alert: Boolean = false) {
    Surface(modifier = modifier, color = Color.White, shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(icon, null, tint = if (alert) Red else Gold)
            Text(value, fontSize = 27.sp, fontWeight = FontWeight.Bold, color = Ink)
            Text(label, fontSize = 10.sp, color = Muted, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        }
    }
}

@Composable
private fun StockScreen(
    shop: Shop,
    onShop: (Shop) -> Unit,
    search: String,
    onSearch: (String) -> Unit,
    category: String,
    onCategory: (String) -> Unit,
    padding: PaddingValues
) {
    val allProducts = PreviewStock.byShop[shop].orEmpty()
    val categories = listOf("All") + allProducts.map { it.category }.distinct()
    val visible = allProducts.filter {
        (search.isBlank() || it.name.contains(search, ignoreCase = true)) &&
            (category == "All" || it.category == category)
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(15.dp)
    ) {
        item { PageHeader("Stock", "Your inventory, shop by shop.") }
        item { ShopPicker(shop, onShop) }
        item {
            OutlinedTextField(
                value = search,
                onValueChange = onSearch,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Search products") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                shape = RoundedCornerShape(14.dp),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Gold,
                    unfocusedBorderColor = Color(0xFFE2DED5)
                )
            )
        }
        item {
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                categories.forEach { item ->
                    FilterChip(
                        selected = category == item,
                        onClick = { onCategory(item) },
                        label = { Text(item) },
                        colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Navy, selectedLabelColor = Gold)
                    )
                }
            }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${visible.size} products", fontWeight = FontWeight.Bold, color = Ink)
                Spacer(Modifier.weight(1f))
                Text("PREVIEW DATA", color = Muted, fontSize = 9.sp, letterSpacing = 1.sp)
            }
        }
        if (visible.isEmpty()) {
            item { Text("No products match this search.", color = Muted, modifier = Modifier.padding(vertical = 24.dp)) }
        } else {
            items(visible) { ProductRow(it) }
        }
        item {
            OutlinedButton(
                onClick = {},
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Navy)
            ) { Icon(Icons.Default.Add, null); Spacer(Modifier.width(8.dp)); Text("Add product") }
        }
    }
}

@Composable
private fun ProductRow(product: StockPreview) {
    Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(color = Navy.copy(alpha = .07f), shape = RoundedCornerShape(12.dp)) {
                Icon(Icons.Default.Inventory2, null, tint = Navy, modifier = Modifier.padding(12.dp))
            }
            Column(Modifier.weight(1f).padding(start = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(product.name, fontWeight = FontWeight.SemiBold, color = Ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${product.category} · ${product.sellingPrice}", color = Muted, fontSize = 11.sp)
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("${product.quantity}", fontWeight = FontWeight.Bold, color = Ink, fontSize = 17.sp)
                Text(product.unit, color = Muted, fontSize = 10.sp)
                if (product.isLowStock) Text("LOW", color = Red, fontSize = 9.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun PlaceholderScreen(title: String, description: String, icon: androidx.compose.ui.graphics.vector.ImageVector, padding: PaddingValues) {
    Column(
        Modifier.fillMaxSize().padding(padding).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Surface(color = Navy, shape = RoundedCornerShape(24.dp)) {
            Icon(icon, null, tint = Gold, modifier = Modifier.padding(24.dp).size(36.dp))
        }
        Spacer(Modifier.height(20.dp))
        Text(title, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Ink)
        Spacer(Modifier.height(8.dp))
        Text(description, color = Muted, fontSize = 13.sp)
        Spacer(Modifier.height(12.dp))
        Text("COMING IN THE NEXT BUILD", color = Green, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
    }
}
