import os
from pathlib import Path
from pathlib import Path

from sarvamai import SarvamAI

# ponytail: tiny .env loader instead of python-dotenv; no quotes/export support
env_file = Path(__file__).with_name(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

def get_api_key():
    if not os.environ.get("SARVAM_API_KEY", "").strip():
        env_file = Path(__file__).with_name(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                name, separator, value = line.partition("=")
                if separator and name.strip() == "SARVAM_API_KEY":
                    os.environ["SARVAM_API_KEY"] = value.strip().strip("\"'")
                    break
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Save SARVAM_API_KEY in .env before starting.")
    return key


if __name__ == "__main__":
    client = SarvamAI(api_subscription_key=get_api_key())
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[{"role": "user", "content": "Say hello in one short sentence."}],
    )
    print(response.choices[0].message.content)
