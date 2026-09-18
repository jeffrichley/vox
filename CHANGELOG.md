# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.6](https://github.com/jeffrichley/vox/compare/v0.2.5...v0.2.6) (2026-09-18)


### Features

* **config:** Continuous hotkey and Pause length settings ([#47](https://github.com/jeffrichley/vox/issues/47)) ([d7f0d43](https://github.com/jeffrichley/vox/commit/d7f0d43afae1af8a278e16da41b887403cdea28b))
* **continuous:** idle auto-off after continuous_idle_minutes ([#49](https://github.com/jeffrichley/vox/issues/49)) ([e811f10](https://github.com/jeffrichley/vox/commit/e811f108cc538dc0c1dfcfc9b2d5ee9a98bbeedb))
* **continuous:** junk guard for short sounds and Whisper hallucinations ([#36](https://github.com/jeffrichley/vox/issues/36)) ([#51](https://github.com/jeffrichley/vox/issues/51)) ([8d2762a](https://github.com/jeffrichley/vox/commit/8d2762ab3579155c1f9e238d1e2c7360c1cb5624))
* **continuous:** live speech detection adapter ([#33](https://github.com/jeffrichley/vox/issues/33)) ([#43](https://github.com/jeffrichley/vox/issues/43)) ([96ac678](https://github.com/jeffrichley/vox/commit/96ac6780365fa6ed0d785e1adb3983ba90cd3593))
* **continuous:** modifier-key safety for Continuous dictation ([#39](https://github.com/jeffrichley/vox/issues/39)) ([#52](https://github.com/jeffrichley/vox/issues/52)) ([b571f47](https://github.com/jeffrichley/vox/commit/b571f470a5014f60ffeb15f4eca27cd9eb2e1543))
* **continuous:** never fail Continuous dictation silently ([#38](https://github.com/jeffrichley/vox/issues/38)) ([#50](https://github.com/jeffrichley/vox/issues/50)) ([652f5ea](https://github.com/jeffrichley/vox/commit/652f5eacde747c3f6aedd75fa899932bde12a3a6))
* **continuous:** show Continuous state in Stop window and tray ([#40](https://github.com/jeffrichley/vox/issues/40)) ([#53](https://github.com/jeffrichley/vox/issues/53)) ([05dddbf](https://github.com/jeffrichley/vox/commit/05dddbf9311b5a7804aff0c21b7b51daf521cafa))
* **continuous:** toggle Continuous dictation and Commit on Pause ([#42](https://github.com/jeffrichley/vox/issues/42)) ([672647e](https://github.com/jeffrichley/vox/commit/672647e58a5a867dc35831daa2c9811960d172a7))
* **inject:** restore previous clipboard text after paste ([#45](https://github.com/jeffrichley/vox/issues/45)) ([f9da88d](https://github.com/jeffrichley/vox/commit/f9da88d3ad1d7f3cec662f7fc80f38779a6a6e20))
* **settings:** Continuous dictation fields in settings window ([#41](https://github.com/jeffrichley/vox/issues/41)) ([#54](https://github.com/jeffrichley/vox/issues/54)) ([7ca4936](https://github.com/jeffrichley/vox/commit/7ca49365e18d017971bcfe52aeb8a12821c0359c))


### Bug Fixes

* **config:** default Continuous hotkey to ctrl+alt+d ([#48](https://github.com/jeffrichley/vox/issues/48)) ([974d820](https://github.com/jeffrichley/vox/commit/974d820ed7b7d654ce8e9739c65ea92fd740461f))


### Documentation

* **continuous:** close out Continuous dictation parent [#31](https://github.com/jeffrichley/vox/issues/31) ([#55](https://github.com/jeffrichley/vox/issues/55)) ([00e0df0](https://github.com/jeffrichley/vox/commit/00e0df08b153f2028bb502455a6b01a9a955e4fe))

## [0.2.5](https://github.com/jeffrichley/vox/compare/v0.2.4...v0.2.5) (2026-05-15)


### Bug Fixes

* **ci:** make pip-audit non-blocking ([#22](https://github.com/jeffrichley/vox/issues/22)) ([397decd](https://github.com/jeffrichley/vox/commit/397decd91cece7d9c623f6dc8b983a285f665090))

## [0.2.4](https://github.com/jeffrichley/vox/compare/v0.2.3...v0.2.4) (2026-03-24)


### Bug Fixes

* **settings:** make hotkey capture and runtime rebinding reliable ([cf5bace](https://github.com/jeffrichley/vox/commit/cf5bace1978694f6edf61a031e173a3c941dec86))


### Documentation

* **plan:** close tray packaging validation ([969e081](https://github.com/jeffrichley/vox/commit/969e0816df9c504c4ffa269ffd0e088edac77fad))

## [0.2.3](https://github.com/jeffrichley/vox/compare/v0.2.2...v0.2.3) (2026-03-18)


### Bug Fixes

* **cli/workflow:** make PyInstaller --help headless-safe ([5762345](https://github.com/jeffrichley/vox/commit/5762345b8e951f66e5fa738750c1a9f4b4add383))
* **cli:** lazy import audio/hotkey modules ([e4f53e4](https://github.com/jeffrichley/vox/commit/e4f53e420557017fadd472edc4b57a3baf439502))

## [0.2.2](https://github.com/jeffrichley/vox/compare/v0.2.1...v0.2.2) (2026-03-18)


### Bug Fixes

* **build:** lazy-load sounddevice; set release tag for upload ([c7060cb](https://github.com/jeffrichley/vox/commit/c7060cbeac6c7c5a98b5f54a0ce43f0daeda9ef5))
* trigger patch release ([81f12a0](https://github.com/jeffrichley/vox/commit/81f12a07b89b3f89e2cdfa64d75ff4bd3d668f05))

## [0.2.1](https://github.com/jeffrichley/vox/compare/v0.2.0...v0.2.1) (2026-03-18)


### Bug Fixes

* trigger patch release ([9498261](https://github.com/jeffrichley/vox/commit/9498261a0adea5f116205f8fc3bafb30f709037d))

## [0.2.0](https://github.com/jeffrichley/vox/compare/v0.1.0...v0.2.0) (2026-03-17)


### Features

* **packaging:** default vox command, tray, PyPI and release assets ([#2](https://github.com/jeffrichley/vox/issues/2)) ([8a59541](https://github.com/jeffrichley/vox/commit/8a595413efc66c2de4afb209c704565423e5a0e3))

## [Unreleased]

- Initial push-to-talk MVP, system tray, default command UX, PyPI packaging.
