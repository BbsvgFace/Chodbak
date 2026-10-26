import base64
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import httpx

from chat import get_api_key
from chodbak_codex import Patrol, apologised, decode_audio, matches, parse_lines, prepare_session, terms
from chodbak_codex import AudioPlayer, Chodbak, preparation_error


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    return stream.getvalue()


class WatchdogTests(unittest.TestCase):
    def test_only_departures_escalate(self):
        patrol = Patrol()
        self.assertEqual(patrol.observe(False), 0)
        for stage in (1, 2, 3, 3):
            self.assertEqual(patrol.observe(True), 0)
            self.assertEqual(patrol.observe(True), 0)
            self.assertEqual(patrol.observe(False), stage)
            self.assertEqual(patrol.observe(False), 0)

    def test_exact_app_or_partial_title(self):
        apps, titles = terms("Notepad.exe, figma"), terms("Thesis, Sarvam")
        self.assertTrue(matches("NOTEPAD.EXE", "Untitled", apps, titles))
        self.assertTrue(matches("figma.exe", "", apps, titles))
        self.assertTrue(matches("chrome.exe", "My THESIS - Chrome", apps, titles))
        self.assertFalse(matches("notepad-fake.exe", "Other", apps, titles))
        self.assertEqual(terms(" , , "), ())

    def test_apology_is_the_new_unlock_phrase(self):
        self.assertTrue(apologised(" SORRY   mummy "))
        for text in ("promise", "chodi mat kar", "sorry", "sorry mummy please"):
            self.assertFalse(apologised(text))

    def test_env_file_and_environment_precedence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            fake_script = Path(folder) / "chat.py"
            (Path(folder) / ".env").write_text('SARVAM_API_KEY="fixture-only"\n')
            with patch("chat.__file__", str(fake_script)), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(get_api_key(), "fixture-only")
                os.environ["SARVAM_API_KEY"] = "environment-fixture"
                self.assertEqual(get_api_key(), "environment-fixture")
                os.environ["SARVAM_API_KEY"] = ""
                (Path(folder) / ".env").write_text("SARVAM_API_KEY=\n")
                with self.assertRaises(RuntimeError):
                    get_api_key()

    def test_model_output_validation(self):
        lines = {key: "text" for key in ("warning", "taunt", "last", "caption", "hostage")}
        self.assertEqual(parse_lines(json.dumps(lines)), lines)
        for invalid in ("null", "[]", "{}", json.dumps({**lines, "last": 3}),
                        json.dumps({**lines, "last": "x" * 241})):
            with self.assertRaises(ValueError):
                parse_lines(invalid)

    def test_audio_validation(self):
        data = wav_bytes()
        self.assertEqual(decode_audio(base64.b64encode(data)), data)
        with self.assertRaises((ValueError, wave.Error, EOFError)):
            decode_audio(base64.b64encode(b"not audio"))

    @patch("chodbak_codex.SarvamAI")
    def test_three_local_audio_clips_and_mom_question_last(self, sdk):
        client = sdk.return_value
        lines = dict(warning="warning", taunt="taunt", last="mom question", caption="caption", hostage="pixel agent")
        client.chat.completions.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(lines)))])
        client.text_to_speech.convert.return_value = SimpleNamespace(
            audios=[base64.b64encode(wav_bytes()).decode()])
        result = prepare_session("fixture-only", "Hindi", threading.Event())
        self.assertEqual(len(result[1]), 3)
        calls = client.text_to_speech.convert.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1].kwargs["text"], "caption pixel agent mom question")
        self.assertEqual(calls[-1].kwargs["language_code"], "hi-IN")
        prompt = str(client.chat.completions.call_args.kwargs["messages"])
        self.assertNotIn("chrome.exe", prompt)

    @patch("chodbak_codex.SarvamAI")
    def test_cancellation_stops_followup_speech_requests(self, sdk):
        cancelled = threading.Event()
        cancelled.set()
        lines = dict(warning="one", taunt="two", last="three", caption="four", hostage="five")
        sdk.return_value.chat.completions.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(lines)))])
        self.assertIsNone(prepare_session("fixture-only", "Tamil", cancelled))
        sdk.assert_not_called()

    def test_errors_do_not_expose_request_secrets(self):
        error = httpx.ConnectError("sensitive-request-content")
        message = preparation_error(error)
        self.assertIn("Cannot connect", message)
        self.assertNotIn("sensitive-request-content", message)
        self.assertIn("unusable", preparation_error(ValueError("private-data")))

    @patch("chodbak_codex.winsound.PlaySound")
    @patch("chodbak_codex.ctypes.WinDLL")
    def test_meme_sting_is_capped_and_stop_cancels_speech(self, dll, sound):
        commands = []

        def mci(command, buffer, size, callback):
            commands.append(command)
            if " length" in command:
                buffer.value = "9000"
            return 0

        dll.return_value.mciSendStringW.side_effect = mci
        root = unittest.mock.Mock()
        root.after.return_value = "scheduled-speech"
        player = AudioPlayer(root, unittest.mock.Mock())
        with patch.object(Path, "exists", return_value=True):
            player.play(Path("speech.wav"), Path("sting.mp3"))
        self.assertIn(f"play {player.alias} from 0 to 2000", commands)
        self.assertEqual(root.after.call_args.args[0], 2040)
        player.stop()
        root.after_cancel.assert_called_once_with("scheduled-speech")
        sound.assert_called_with(None, 0)

    @patch("chodbak_codex.winsound.PlaySound")
    @patch("chodbak_codex.ctypes.WinDLL")
    def test_missing_sting_still_plays_speech(self, dll, sound):
        player = AudioPlayer(unittest.mock.Mock(), unittest.mock.Mock())
        with patch.object(Path, "exists", return_value=False):
            player.play(Path("speech.wav"), Path("missing.mp3"))
        self.assertEqual(sound.call_args.args[0], "speech.wav")


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp_patch = patch("tempfile.tempdir", str(Path(__file__).parent))
        self.temp_patch.start()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Chodbak(self.root)
        self.app.play = unittest.mock.Mock()
        self.app.photo = tk.PhotoImage(master=self.root, width=100, height=100)
        self.app.lines = dict(warning="warning", taunt="taunt", last="मम्मी को बुलाऊँ?",
                              caption="disappointed", hostage="fictional agent")

    def tearDown(self):
        self.app.close()
        self.temp_patch.stop()

    def test_popup_cap_apology_and_stop(self):
        for stage, count in ((1, 1), (2, 1), (3, 3)):
            self.app.show_warning(stage)
            self.root.update_idletasks()
            self.assertEqual(len(self.app.alerts), count)
        self.app.closed_locked_popup()
        self.app.apologise("promise")
        self.assertEqual(len(self.app.alerts), 3)
        self.app.apologise("sorry mummy")
        self.assertEqual(len(self.app.alerts), 0)
        self.assertFalse(self.app.running)
        self.assertFalse(self.app.locked)
        self.assertIn("restored", self.app.status.get())

    def test_countdown_only_changes_fictional_sprite(self):
        self.app.show_warning(3)
        self.app.running = True
        self.app.locked_at = time.monotonic() - 31
        self.app.poll()
        self.assertTrue(self.app.executed)
        self.assertIn("Only pixels", self.app.agent_status.get())
        self.app.stop()
        self.assertFalse(self.app.running)
        self.assertEqual(len(self.app.alerts), 0)

    def test_language_is_required_before_photo_or_api(self):
        self.app.photo = None
        with patch("chodbak_codex.get_api_key") as key, patch.object(self.app, "choose_photo") as photo:
            self.app.start()
            key.assert_not_called()
            photo.assert_not_called()
        self.assertIn("language first", self.app.status.get())

    def test_late_results_cannot_restart_stopped_session(self):
        old_session = self.app.session
        self.app.stop()
        self.app.results.put((old_session, (self.app.lines, [wav_bytes()] * 3), None))
        self.app.poll()
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.sounds, [])


if __name__ == "__main__":
    unittest.main()
