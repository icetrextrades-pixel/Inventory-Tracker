package zw.co.mutowei.app.data

import android.content.Context
import androidx.room.Room

object DatabaseProvider {
    @Volatile private var instance: MutoweiDatabase? = null

    fun get(context: Context): MutoweiDatabase =
        instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                MutoweiDatabase::class.java,
                "mutowei-local.db"
            ).fallbackToDestructiveMigration().build().also { instance = it }
        }
}
