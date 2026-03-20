"""Unit tests for audio cue preload, decode, cache, and playback."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from vox import audio_cues
from vox.audio_cues import CuePlaybackError, CuePlayer, CuePreloadError, CueSound


@pytest.mark.unit
class TestPreloadDefaultCues:
    """preload_default_cues caches the module-level default cue player."""

    def test_preload_default_cues_caches_loaded_player(self) -> None:
        """Repeated preload calls reuse the same cached cue player."""
        # Arrange - reset module cache and mock load_default
        player = mock.Mock(spec=CuePlayer)
        with (
            mock.patch.dict(audio_cues._DEFAULT_CUES_STATE, {"player": None}),
            mock.patch.object(
                CuePlayer, "load_default", return_value=player
            ) as mock_load,
        ):
            # Act - preload twice without forcing a reload
            first = audio_cues.preload_default_cues(force_reload=True)
            second = audio_cues.preload_default_cues()

        # Assert - one real load, same cached object returned
        assert first is player
        assert second is player
        mock_load.assert_called_once()

    def test_preload_default_cues_force_reload_replaces_cache(self) -> None:
        """Forced reload replaces the cached cue player instance."""
        # Arrange - reset module cache and return two different players
        first_player = mock.Mock(spec=CuePlayer)
        second_player = mock.Mock(spec=CuePlayer)
        with (
            mock.patch.dict(audio_cues._DEFAULT_CUES_STATE, {"player": None}),
            mock.patch.object(
                CuePlayer,
                "load_default",
                side_effect=[first_player, second_player],
            ) as mock_load,
        ):
            # Act - load once, then force a reload
            first = audio_cues.preload_default_cues(force_reload=True)
            second = audio_cues.preload_default_cues(force_reload=True)

        # Assert - cache was replaced
        assert first is first_player
        assert second is second_player
        assert mock_load.call_count == 2


@pytest.mark.unit
class TestCueResourcePath:
    """_cue_resource_path validates packaged cue assets."""

    def test_cue_resource_path_raises_when_packaged_asset_missing(self) -> None:
        """Missing packaged cue assets raise an actionable preload error."""
        # Arrange - package root without cue asset
        with (
            mock.patch("vox.audio_cues.files", return_value=Path("missing-root")),
            pytest.raises(CuePreloadError, match=r"Missing packaged cue asset"),
        ):
            # Act - resolve a missing packaged cue asset
            audio_cues._cue_resource_path("start")

        # Assert - the missing asset was surfaced as a preload error
        assert True


@pytest.mark.unit
class TestDecodeCue:
    """_decode_cue normalizes PyAV decode output into float32 mono PCM."""

    def test_decode_cue_returns_float32_mono_samples(self) -> None:
        """Decoded cue audio is flattened to mono float32 samples plus rate."""
        # Arrange - fake PyAV container, stream, resampler, and decoded frames
        frame_one = mock.Mock()
        frame_one.to_ndarray.return_value = np.array([[0.25, -0.5]], dtype=np.float32)
        frame_two = mock.Mock()
        frame_two.to_ndarray.return_value = np.array([[1.5, -2.0]], dtype=np.float32)

        mock_container = mock.MagicMock()
        mock_container.streams.audio = [SimpleNamespace(rate=48_000)]
        mock_container.decode.return_value = [object(), object()]
        mock_container.__enter__.return_value = mock_container
        mock_container.__exit__.return_value = None

        mock_resampler = mock.Mock()
        mock_resampler.resample.side_effect = [[frame_one], [frame_two], []]

        fake_av = SimpleNamespace(
            open=mock.Mock(return_value=mock_container),
            audio=SimpleNamespace(
                resampler=SimpleNamespace(
                    AudioResampler=mock.Mock(return_value=mock_resampler)
                )
            ),
        )

        with mock.patch("vox.audio_cues._av", return_value=fake_av):
            # Act - decode the cue
            cue = audio_cues._decode_cue(Path("start.mp3"), "start")

        # Assert - mono float32 array and sample rate preserved
        assert cue.sample_rate == 48_000
        assert cue.samples.dtype == np.float32
        assert cue.samples.shape == (4, 1)
        np.testing.assert_allclose(
            cue.samples[:, 0],
            np.array([0.25, -0.5, 1.0, -1.0], dtype=np.float32),
        )

    def test_decode_cue_raises_when_decode_fails(self) -> None:
        """Decode failures are wrapped in an actionable preload error."""
        # Arrange - av.open raises an exception
        fake_av = SimpleNamespace(open=mock.Mock(side_effect=ValueError("bad mp3")))
        with (
            mock.patch("vox.audio_cues._av", return_value=fake_av),
            pytest.raises(CuePreloadError, match=r"Failed to decode packaged"),
        ):
            # Act - decode a broken cue asset
            audio_cues._decode_cue(Path("bad.mp3"), "start")

        # Assert - the decode failure was wrapped as a preload error
        assert True


@pytest.mark.unit
class TestCuePlayback:
    """CuePlayer dispatches playback non-blockingly and wraps failures."""

    def test_play_start_dispatches_non_blocking_sounddevice_play(self) -> None:
        """play_start uses sounddevice.play with blocking disabled."""
        # Arrange - cue player with one preloaded start cue
        start = CueSound(samples=np.ones((3, 1), dtype=np.float32), sample_rate=16_000)
        end = CueSound(samples=np.zeros((2, 1), dtype=np.float32), sample_rate=16_000)
        player = CuePlayer(start=start, end=end)
        mock_sd = mock.Mock()

        with mock.patch("vox.audio_cues._sd", return_value=mock_sd):
            # Act - play the start cue
            player.play_start(volume_scale=0.5)

        # Assert - sounddevice.play called non-blocking with the scaled samples
        mock_sd.play.assert_called_once()
        args, kwargs = mock_sd.play.call_args
        np.testing.assert_allclose(args[0], np.full((3, 1), 0.5, dtype=np.float32))
        assert kwargs == {"samplerate": 16_000, "blocking": False}

    def test_play_end_raises_playback_error_when_output_device_fails(self) -> None:
        """Playback failures are wrapped in CuePlaybackError."""
        # Arrange - cue player and failing sounddevice module
        cue = CueSound(samples=np.zeros((2, 1), dtype=np.float32), sample_rate=16_000)
        player = CuePlayer(start=cue, end=cue)
        mock_sd = mock.Mock()
        mock_sd.play.side_effect = RuntimeError("device unavailable")

        with (
            mock.patch("vox.audio_cues._sd", return_value=mock_sd),
            pytest.raises(CuePlaybackError, match=r"Failed to play"),
        ):
            # Act - play a cue against a failing output device
            player.play_end()

        # Assert - the playback failure was wrapped as CuePlaybackError
        assert True
