"""UserPromptSubmit hint hook. Reads the hook JSON on stdin, prints a one or two line hint (JSON
additionalContext) when the prompt looks keep-worthy or matches an existing wiki page. Silent otherwise.
Never fails: any error means no output and exit 0. Hints carry titles and paths only, never page bodies."""
import json
import re
import sys
import unicodedata

from . import checkpoint, config, search, util
from .vault import Vault

MIN_CHARS = 25
STOP = set("""about above after again also another because before being between could does doing
from have having here into just like make more most much need only other over please should some
such than that their them then there these they this those through very want what when where which
while will with would your""".split())
KEEP_CUES = re.compile(
    r"\b(?:(?:remember this|note to self|worth keeping|keep this|save this|we decided|i decided|"
    r"good idea|someday)\b|(?:decision|idea):)", re.I)


NO_SPACES = re.compile("[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u2e80-\U0010ffff]")


def _user_words() -> tuple:
    """(keep cues, stop words) from `hook` in config.json, e.g. phrases in the user's language."""
    section = config.load().get("hook")
    out = []
    for key in ("keep_cues", "stop_words"):
        words = section.get(key) if isinstance(section, dict) else None
        out.append([w.strip() for w in words if isinstance(w, str) and w.strip()] if isinstance(words, list) else [])
    return tuple(out)


def _fold(text: str) -> str:
    """Case and accents off, punctuation kept, full length."""
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


def _keep_cue(prompt: str, cues=()) -> bool:
    if KEEP_CUES.search(util.slugify(prompt).replace("-", " ")) or KEEP_CUES.search(prompt):
        return True
    if not cues:
        return False
    text = _fold(prompt)
    for cue in map(_fold, cues):
        # Whole words only, except in scripts written without spaces (Thai, Lao, Burmese, Khmer, CJK).
        edge = [c.isalnum() and not NO_SPACES.match(c) for c in (cue[:1], cue[-1:]) if c]
        if len(edge) == 2 and re.search((r"(?<!\w)" if edge[0] else "") + re.escape(cue)
                                        + (r"(?!\w)" if edge[1] else ""), text):
            return True
    return False


def _terms(prompt: str, stop_words=()) -> list:
    folded = util.slugify(prompt).replace("-", " ")
    stop = STOP | {util.slugify(w) for w in stop_words}
    seen, out = set(), []
    for w in folded.split():
        if len(w) >= 5 and w not in stop and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:8]


def hint_for(prompt: str, vault: Vault = None) -> str:
    """Return the hint text, or "" when nothing is relevant."""
    prompt = (prompt or "").strip()
    if len(prompt) < MIN_CHARS or prompt.startswith("/") or util.privacy_scan(prompt):
        return ""
    lines = []
    cues, stop_words = _user_words()
    if _keep_cue(prompt, cues):
        lines.append("Mentat: this may be worth capturing; follow the capture protocol (propose, then ask once).")
    terms = _terms(prompt, stop_words)
    if vault is not None and len(terms) >= 2:
        hits = []
        for path, _type, _domain, title, summary in search.find(vault, " ".join(terms), limit=5, sync=False):
            hay = util.slugify(f"{title} {summary}").replace("-", " ")
            if sum(t in hay for t in terms) >= 2:
                hits.append(f"[[{path.rsplit('/', 1)[-1].removesuffix('.md')}]] ({path})")
            if len(hits) == 2:
                break
        if hits:
            lines.append("Mentat: related vault pages: " + "; ".join(hits)
                         + f". Read them with `{config.command()} find` or the file path if relevant.")
    return "\n".join(lines)


def main() -> None:
    try:
        util.utf8_stdio()
        data = json.loads(sys.stdin.read() or "{}")
        checkpoint.record(data)  # resume point if the session dies before /wrap; ids only, no prompt text
        cwd = config.hook_cwd(data)
        root = config.vault_root()
        if root is None or not (config.in_vault(cwd, root) or config.project_for(cwd)):
            return
        vault = Vault(root)
        vault.check()
        text = hint_for(data.get("prompt", ""), vault)
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": text}}, ensure_ascii=False))
    except BaseException:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
