# CHODBAK / Chodi mat kar

A Windows pixel-art focus patrol. Python + `sarvamai`; no other dependencies.

1. Save your Sarvam key in `.env` as `SARVAM_API_KEY=...`.
2. Run `py chodbak_codex.py` (or use your installed Python executable) in a normal Windows session with internet access.
3. Choose your language first, then a local PNG/GIF photo, then app process names or window-title fragments.
4. Click **Report for duty**. Preparation makes one chat request and three text-to-speech requests; these use API credits. Then open a watched window to arm tracking.
5. Each departure escalates: spoken warning, spoken roast, then three popups with a photo reveal, fictional pixel-agent countdown, and the translated **Should I call your mom?** as the final spoken taunt.
6. Type **sorry mummy** in any third-level popup and press Enter to clear everything and end the session. **Emergency Stop**, Escape while a Chodbak window has focus, or closing the main window also stops the session and audio.

App rules match process names exactly, with optional `.exe`. Title rules match fragments. Any rule can allow a window. For a specific browser tab, enter its title fragment and leave the browser app out of the app rules. Warnings follow a switch; transitions shorter than the 350 ms polling interval can be missed. The watchdog's own controls and unreadable processes are ignored.

Each warning starts with a supplied meme sting from `New folder`, capped at two seconds, followed by its Sarvam voice clip. The metal pipe introduces level one, the cat laugh introduces level two, and level three alternates randomly between FAAAA and Ye le. Missing or unsupported SFX are skipped so speech still plays. The third audio repeats at intervals of at least 25 seconds, allowing the full speech clip to finish. Emergency Stop immediately cancels both the sting and pending speech.

The 30-second agent countdown is fiction: no coding agents or other applications are controlled or terminated. There is no phone calling or microphone capture; the apology is typed. PNG/GIF photos stay in memory, window titles stay local, and generated audio stays in temporary local WAV files until the app closes. Sarvam receives only the chosen language/persona prompts and generated speech text.

`py -m unittest -v test_chodbak.py` runs isolated tests with mocked Sarvam clients; it makes no API calls. `py chat.py` makes the original short live hello call using the environment or `.env`.

API references: [Chat V1](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1), [Text to speech](https://docs.sarvam.ai/api-reference/text-to-speech/convert).
