package zw.co.mutowei.app

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private data class ReleaseInfo(
    val tag: String,
    val title: String,
    val notes: String,
    val pageUrl: String
)

@Composable
fun UpdateScreen(padding: PaddingValues) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var checking by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Check GitHub for the latest approved Mutowei release.") }
    var release by remember { mutableStateOf<ReleaseInfo?>(null) }
    var hasUpdate by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Column(
        modifier = Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("App updates", fontSize = 25.sp, fontWeight = FontWeight.Bold)
        Text("Check for new approved versions without searching through build artifacts.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Card {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Default.SystemUpdate, contentDescription = null, tint = MaterialTheme.colorScheme.secondary, modifier = Modifier.size(32.dp))
                Text("Installed version", fontWeight = FontWeight.SemiBold)
                Text("Version " + installedVersionName(context) + " (" + installedVersionCode(context) + ")")
                Text(message, style = MaterialTheme.typography.bodyMedium)
                if (checking) LinearProgressIndicator(Modifier.fillMaxWidth())
                Button(
                    enabled = !checking,
                    onClick = {
                        scope.launch {
                            checking = true
                            error = null
                            release = null
                            try {
                                val latest = withContext(Dispatchers.IO) { fetchLatestRelease() }
                                release = latest
                                val latestCode = latest.tag.removePrefix("v").substringBefore(".").toIntOrNull()
                                hasUpdate = latestCode != null && latestCode > installedVersionCode(context)
                                message = if (hasUpdate) "A newer release is available: " + latest.tag else "You are using the latest published release, or its version tag is not newer."
                            } catch (e: Exception) {
                                error = e.message ?: "Could not check for updates."
                                message = "Update check failed. Check your internet connection and try again."
                            } finally {
                                checking = false
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (checking) "Checking…" else "Check for updates") }
            }
        }
        release?.let { info ->
            Card {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(if (hasUpdate) "Update available" else "Latest published release", fontWeight = FontWeight.Bold)
                    Text(info.title + " · " + info.tag)
                    if (info.notes.isNotBlank()) Text(info.notes, style = MaterialTheme.typography.bodySmall, maxLines = 8)
                    Button(
                        onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(info.pageUrl))) },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (hasUpdate) "Open release to update" else "View release") }
                    Text("Android will ask before installation. Keeping existing app data requires every update to use the same signing key.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if (error != null) Text(error!!, color = MaterialTheme.colorScheme.error)
        Text("Updates are checked against the official GitHub Releases page. The app never installs software silently.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun installedVersionName(context: android.content.Context): String {
    @Suppress("DEPRECATION")
    return context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "unknown"
}

private fun installedVersionCode(context: android.content.Context): Int {
    @Suppress("DEPRECATION")
    return context.packageManager.getPackageInfo(context.packageName, 0).versionCode
}

private fun fetchLatestRelease(): ReleaseInfo {
    val connection = URL("https://api.github.com/repos/icetrextrades-pixel/Inventory-Tracker/releases/latest")
        .openConnection() as HttpURLConnection
    connection.requestMethod = "GET"
    connection.connectTimeout = 10000
    connection.readTimeout = 10000
    connection.setRequestProperty("Accept", "application/vnd.github+json")
    connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
    try {
        if (connection.responseCode != 200) throw IllegalStateException("No published release was found yet.")
        val json = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        return ReleaseInfo(
            tag = json.optString("tag_name"),
            title = json.optString("name").ifBlank { json.optString("tag_name") },
            notes = json.optString("body"),
            pageUrl = json.optString("html_url")
        )
    } finally {
        connection.disconnect()
    }
}
