# CHODBAK / Chodi mat kar

A desi pixel-art focus watchdog for Windows. Leave the apps you're meant to be working in and a strict desi havaldar shouts at you, out loud, in your own language (12 Indian languages + English, voiced by [Sarvam AI](https://www.sarvam.ai/)).

## Download (Windows 10/11)

1. **[Download Chodbak.exe](https://github.com/BbsvgFace/Chodbak/raw/main/download/Chodbak.exe)** (or open the `download` folder above and click *Download raw file*).
2. Put it in its own folder, e.g. `Documents\Chodbak`. Your settings are saved next to it.
3. Double-click it. Windows SmartScreen may say *"Windows protected your PC"* because the exe isn't code-signed: click **More info → Run anyway**. Some antivirus tools also flag PyInstaller apps by mistake; the full source is in this repo if you'd rather run that.
4. First run asks for:
   - your **Sarvam API key**: free at [dashboard.sarvam.ai](https://dashboard.sarvam.ai) → *API Keys*. It's saved only in `.env` next to the exe.
   - the **language you speak at home**
   - the **apps / tabs to stay in**, comma separated: a window title or exe name, e.g. `Visual Studio Code, Notion, chrome.exe`
   - a **photo** (it won't say why)
5. Keep working. Close the black CHODBAK window to stop it.

You need internet (Sarvam writes and voices the live taunts) and speakers. A mic is optional.

## What happens

| Strike | What you get |
|---|---|
| 1 · SAAVDHAN! | Pixel warning, *FAAAA!*, spoken taunt |
| 2 · RUK JA, NALAYAK! | Cat laugh, your photo in a marigold frame, "disappointed hain tujhse", fake family WhatsApp gossip (*ye le*) |
| 3 · KHATRA! KHATRA! | Metal pipe, drags you back to work, cooker whistle, flying chappal, threatens your coding agent (a joke: nothing is ever closed), then *"should I call your mummy?"* in your language with a fake call |

Strike 3 only ends when you say **"sorry mummy"** into the mic (or type it if there's no mic). While you stay away it keeps nagging with fresh pre-recorded regional taunts. Stay focused for 25 minutes straight and you earn a chai break.

## Run from source

```
pip install sarvamai
python chodbak.py                 # first run asks everything, like the exe
python chodbak.py --test 3        # preview a strike
python chodbak.py --setup         # redo the questions
python chodbak.py --make-taunts   # re-record the regional taunt bank in taunts/ (uses API credits)
python build_exe.py               # rebuild download/Chodbak.exe (needs: pip install pyinstaller)
```

Put your key in `.env` as `SARVAM_API_KEY=...`, or let the first run ask for it. `.env`, your photo and your preferences are git-ignored.

## Alternative version (`chodbak_codex.py`)

A settings-window version made in a parallel session: choose language, a PNG/GIF photo, and app process names or title fragments, then click **Report for duty**. It prepares one chat request and three voice clips per session; strike 3 opens three popups (photo, a fictional "Agent 404" countdown, the translated *Should I call your mom?*) and ends when you type **sorry mummy**. Its meme stings are read from a local `New folder` that isn't in this repo, so it runs without them here. `python -m unittest -v test_chodbak.py` tests it with mocked Sarvam clients.

API references: [Chat](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1), [Text to speech](https://docs.sarvam.ai/api-reference/text-to-speech/convert), [Speech to text](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe), [Translate](https://docs.sarvam.ai/api-reference/text/translate).
