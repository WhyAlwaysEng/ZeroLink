package com.zerocast.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.zerocast.BuildConfig
import com.zerocast.databinding.ActivitySettingsBinding
import com.zerocast.util.UpdateChecker
import com.zerocast.util.ZeroLinkConfig

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupUI()
        setupListeners()
    }

    private fun setupUI() {
        binding.tvAppVersion.text = "Version ${BuildConfig.VERSION_NAME} • Open Source Ecosystem"

        binding.switchKeepAwake.isChecked = ZeroLinkConfig.getKeepScreenAwake(this)
        binding.switchHaptics.isChecked = ZeroLinkConfig.getHapticFeedback(this)
        binding.switchFilterBanking.isChecked = ZeroLinkConfig.getPrivacyFilterBanking(this)
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            if (ZeroLinkConfig.getHapticFeedback(this)) {
                it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            }
            finish()
        }

        binding.switchKeepAwake.setOnCheckedChangeListener { view, isChecked ->
            if (ZeroLinkConfig.getHapticFeedback(this)) {
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            }
            ZeroLinkConfig.setKeepScreenAwake(this, isChecked)
        }

        binding.switchHaptics.setOnCheckedChangeListener { view, isChecked ->
            ZeroLinkConfig.setHapticFeedback(this, isChecked)
            if (isChecked) {
                view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            }
        }

        binding.switchFilterBanking.setOnCheckedChangeListener { view, isChecked ->
            if (ZeroLinkConfig.getHapticFeedback(this)) {
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            }
            ZeroLinkConfig.setPrivacyFilterBanking(this, isChecked)
            val msg = if (isChecked) "Banking apps will be excluded from notification mirroring" else "All notifications will be mirrored"
            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
        }

        binding.btnCheckUpdates.setOnClickListener {
            if (ZeroLinkConfig.getHapticFeedback(this)) {
                it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            }
            UpdateChecker.checkForUpdates(this, isManualCheck = true)
        }

        binding.btnGitHubRepo.setOnClickListener {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/WhyAlwaysEng/ZeroLink"))
            startActivity(intent)
        }

        binding.btnReleases.setOnClickListener {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/WhyAlwaysEng/ZeroLink/releases"))
            startActivity(intent)
        }
    }
}
