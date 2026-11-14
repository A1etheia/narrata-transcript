# TOOL-95 — CLI ohne Startskript: cuBLAS vorladen, `paths.root` verankern

## Ziel
`transcript` läuft aus jedem Einstieg (`.venv/bin/transcript`, `python -m transcript`, Tests) und aus jedem Verzeichnis, ohne `LD_LIBRARY_PATH` und ohne vorher in den Projektordner zu wechseln. Heute klappt das nur über `scripts/transcript`. Das Skript setzt `LD_LIBRARY_PATH` und macht ein `cd` in den Projektordner. Danach ist es überflüssig und wird entfernt.

## Ist-Stand
- `src/transcript/asr/whisper.py:56-70`: `LIBRARY_HINT` verweist auf `LD_LIBRARY_PATH`. `CUDA_LIBRARIES = ("libcublas.so.12",)`, und `missing_cuda_library()` lädt per Soname über `_load_library = ctypes.CDLL`. Diese Funktion nutzt `load()` in `whisper.py:112`, der Preflight nutzt sie in `preflight.py:19,54`.
- `.venv/.../site-packages/nvidia/cublas/lib/libcublas.so.12` kommt aus `nvidia-cublas-cu12` (`pyproject.toml:17`). Die Bibliothek hat `RPATH $ORIGIN`, also wird `libcublasLt.so.12` daneben gefunden.
- `src/transcript/config.py:303`: `root=Path(root)`, das heißt, ein relativer Pfad gilt ab dem aktuellen Verzeichnis. `config/example.yaml:10` und die lokale `config/config.yaml` nutzen `root: .`.
- `src/transcript/__main__.py:64-66`: `_DEFAULT_CONFIG`, `_EXAMPLE_CONFIG` und `_DOTENV` sind relativ zum aktuellen Verzeichnis. `_load_config` in `__main__.py:1625` erkennt den Default am Pfad. Der Token wird über `_DOTENV` gelesen (`__main__.py:661`).
- `scripts/transcript` setzt `LD_LIBRARY_PATH` und macht `cd "$root"`. Getestet wird es in `tests/test_start_script.py`.
- Doku: README Z. 37, 46, 223-230, 314, 705 sowie `docs/ablauf.md` Z. 33-36 und 211.

## Entscheidungen
- **cuBLAS per absolutem Pfad vorladen.** `importlib.util.find_spec("nvidia.cublas")` liefert `lib/libcublas.so.12`. Die Bibliothek wird mit `ctypes.CDLL(path, mode=RTLD_GLOBAL)` geladen. Danach findet CTranslate2 den Soname bereits geladen vor. Fehlt das Paket, gibt es einen Fallback auf das Laden per Soname, damit eine systemweite CUDA weiter funktioniert. Gebündelt wird das in einer Funktion `preload_cuda_libraries()`, die `missing_cuda_library()` ersetzt bzw. speist. `load()` ruft sie vor `WhisperModel` auf.
- **`LIBRARY_HINT`** nennt dann das Whisper-Extra (`pip install -e '.[whisper]'`) statt `LD_LIBRARY_PATH`.
- **Ein relativer `paths.root` gilt ab dem Projektordner.** Der Projektordner ist `PROJECT_ROOT = Path(__file__).resolve().parents[2]`, denn die Installation ist laut README immer editable mit src-Layout. Grund: `root: .` in vorhandenen Configs behält so seine Bedeutung. Die Alternative „relativ zur Config-Datei“ hätte `root: ..` erzwungen und die lokale Config gebrochen.
- **Default-Config, Beispiel und `.env`** liegen absolut unter `PROJECT_ROOT`. Explizite Pfadargumente wie `--config` oder `--from-file` gelten weiter ab dem aktuellen Verzeichnis. Das ergibt sich von selbst, sobald kein `cd` mehr nötig ist.
- **`scripts/transcript` und `tests/test_start_script.py` entfallen.** Das README verlinkt stattdessen `.venv/bin/transcript` nach `~/.local/bin`.
- `asr.model` und `diarization.model` als relativer Ordner bleiben unverändert, weil sie mit Hub-Namen mehrdeutig sind und kein Pilot sie relativ nutzt.

## Daten-Check
- TOOL-66: *handled.* Es werden keine Daten verschoben, nur die Auflösung der Wurzel ändert sich. Vorhandene Sessions unter `input/`, `work/` und `output/` werden weiter gefunden.
- Repo, Log, Fehlermeldung: *handled.* Tests arbeiten in Temp-Ordnern und patchen `_DEFAULT_CONFIG` und `_DOTENV`, damit sie nie die echte `config/config.yaml` oder `.env` lesen. Das gilt besonders für `test_missing_default_file_points_to_the_example` in `tests/test_smoke.py:132`. Fehlermeldungen nennen höchstens Bibliothekspfade.

## Resume-Check
- Abbruch, Wiederverwendung, Modell und Snapshot: *N/A, weil* nur das Laden der Bibliothek und die Pfadauflösung sich ändern. Die ASR-Identität und die Settings bleiben gleich. Ein Resume nach dem Update findet dieselben `work/`-Ordner, denn `root: .` zeigt weiter auf den Projektordner.

## Dependency-Check
- Neue Abhängigkeit: *N/A, weil* `nvidia-cublas-cu12` schon im Whisper-Extra steht (`pyproject.toml:17`). Neu ist nur, dass das Paket direkt per `importlib` angesprochen wird.

## Chunks
### Chunk 1 — cuBLAS vorladen
- Dateien: `src/transcript/asr/whisper.py`, `tests/test_asr_whisper.py`, `tests/test_preflight.py`
- Änderung: `_cublas_path()` über `find_spec`, `preload_cuda_libraries()` mit `RTLD_GLOBAL` und Soname-Fallback. `missing_cuda_library()` nutzt diese Funktion, `load()` lädt vor dem Modell vor, `LIBRARY_HINT` wird neu formuliert. Die Tests prüfen den absoluten Pfad, den Fallback ohne Paket und den Fall „beides fehlt“.
- Verify: `scripts/check`, dann `env -u LD_LIBRARY_PATH .venv/bin/transcript doctor` (cuBLAS ok) und der Whisper-Smoke-Test auf `cuda` ohne `LD_LIBRARY_PATH`.
- AC: `doctor` meldet cuBLAS ok ohne `LD_LIBRARY_PATH`, und der Whisper-Smoke-Test ist auf `cuda` grün.

### Chunk 2 — `paths.root` und Defaults am Projektordner verankern
- Dateien: `src/transcript/config.py`, `src/transcript/__main__.py`, `tests/test_config.py`, `tests/test_smoke.py`
- Änderung: `PROJECT_ROOT` in `config.py`. `load_config` löst einen relativen `root` dagegen auf, ein absoluter bleibt, wie er ist. `_DEFAULT_CONFIG`, `_EXAMPLE_CONFIG` und `_DOTENV` werden zu `PROJECT_ROOT / …`. Die Tests decken relativen und absoluten Root ab, explizites `--config` relativ zum aktuellen Verzeichnis, und der Default-Test patcht auf einen fehlenden Pfad.
- Verify: `scripts/check`, dann aus dem Scratchpad `.venv/bin/transcript config` (Root = Projektordner) und `.venv/bin/transcript status` (Sessions gefunden).
- AC: Ein Aufruf aus einem fremden Verzeichnis findet Config und Sessions, und relative Pfadargumente behalten ihre übliche Bedeutung.

### Chunk 3 — Startskript entfernen, Doku anpassen
- Dateien: `scripts/transcript` (löschen), `tests/test_start_script.py` (löschen), `README.md`, `docs/ablauf.md`, `config/example.yaml` (Kommentar zu `root`)
- Änderung: Im Setup wird `ln -s "$PWD/.venv/bin/transcript" ~/.local/bin/transcript` eingetragen. In Spracherkennung, Doctor-Absatz und Smoke-Test entfällt `LD_LIBRARY_PATH`. Die `paths.root`-Zeile lautet „relativ: ab dem Projektordner“. In `docs/ablauf.md` werden der Startskript-Absatz und die Pilot-Fehler-Abhilfe angepasst.
- Verify: `scripts/check`, und `grep -rn "scripts/transcript\|LD_LIBRARY_PATH" README.md docs/ablauf.md src tests` bleibt leer.
- AC: Die Doku beschreibt nur noch den Weg ohne Startskript.

## Folge-Tickets
- keine [kein Ticket: Scope vollständig im Ticket]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | cuBLAS vorladen in `whisper.py` | no |
| 2 | `paths.root`, Default-Config und `.env` am Projektordner | no |
| 3 | Startskript entfernen, README und `docs/ablauf.md` | no |
