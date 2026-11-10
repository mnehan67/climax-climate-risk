# CLIMAX: Windows → GitHub → public website

This guide assumes the packaged directory **CLIMAX_GitHub_Ready** is on your Windows laptop.

## A. Run the demo on Windows

1. Install **Python 3.11 or newer** from https://www.python.org/downloads/windows/ (select **Add python.exe to PATH** when offered).
2. Extract `CLIMAX_GitHub_Ready.zip` using **Extract All**. Open the extracted `CLIMAX_GitHub_Ready` folder. It should contain `server.py`, `README.md`, and `index.html` directly inside—not another CLIMAX subfolder.
3. Double-click `START_WINDOWS.bat`. Windows may show a security warning for downloaded files; inspect the script first and run only if you trust it.
4. Visit **http://127.0.0.1:5173**. The banner reads **TEST**: the built-in demo works without downloading scientific data. Keep the command window open. Close it to stop the server.
5. Optional: double-click `RUN_PIPELINE_WINDOWS.bat` to fetch/recompute REAL Sentinel-2 / OSM / DEM evidence. This installs scientific Python packages, needs internet, and can fail if public data endpoints are unreachable. Wait for `SUCCESS: Real data ready` before treating any output as REAL.

## B. Create a GitHub repository

1. Install **Git for Windows** from https://git-scm.com/downloads/win.
2. In GitHub, choose **New repository**. Suggested name: `climax-climate-risk`. Leave **Initialize with a README** and **Add .gitignore** unchecked, because both are included here. Create the repository.
3. Open the extracted folder in File Explorer. Click the address bar, type **cmd**, and press Enter. A command prompt opens in this folder.
4. Type these commands one at a time (replace the URL if you chose a different repo name):

```bat
git init
git add .
git status
git commit -m "Initial CLIMAX dashboard and deployment setup"
git branch -M main
git remote add origin https://github.com/mnehan67/climax-climate-risk.git
git push -u origin main
```

Sign in through your browser when Git Credential Manager prompts you. GitHub no longer accepts your account password as a Git HTTPS password. If Git asks you to set an identity before committing, use:

```bat
git config --global user.name "YOUR NAME"
git config --global user.email "YOUR VERIFIED GITHUB EMAIL"
```

Do **not** push `private/.env.local`, API tokens, passwords, or downloaded private bank data. It has been excluded from this prepared archive.

## C. Host the full interactive app with Render

GitHub Pages alone won't run CLIMAX's Python `/api/*` endpoints. Use a **Render Web Service**.

1. Open https://dashboard.render.com/ and sign in.
2. Choose **New → Blueprint**, connect GitHub, select the new `climax-climate-risk` repository, and follow the prompts to apply the included `render.yaml`. Confirm a Free service before accepting.
3. Render will deploy a Python Web Service using the included assets. Open the provided `https://...onrender.com` link. **It will still show TEST until you replace the full data/generated directory with real pipeline outputs.**
4. Open `https://YOUR-SERVICE.onrender.com/api/health`: you should get a JSON object with `"ok":true`.
5. Render may put Free web services to sleep after a period of inactivity. Reloading wakes them.

Alternatively, create **New → Web Service** manually and set: Runtime **Python 3**, Build Command `python -m compileall -q server.py engine.py agent.py memo.py pipeline`, Start Command `python server.py --no-browser`, and Environment Variables `HOST=0.0.0.0` and `CLIMAX_PUBLIC=1`.

## D. Publish later updates

1. Modify and test files locally. If you have successfully run the real pipeline, verify `data/generated/manifest.json` shows `"mode": "REAL"` and that real imagery, buildings and loan layers are all in `data/generated/`.
2. In the same project folder:

```bat
git add .
git commit -m "Update CLIMAX app and data"
git push
```

Render can automatically redeploy the new `main` commit. Always check the live banner afterwards.

## E. Cesium 3D and Claude agent

- MapLibre 3D and all bundled TEST layers work without credentials. An internet connection is required to load Cesium ion aerial imagery/OSM 3D buildings.
- For Cesium's richer map, create your **own** Cesium ion token and set `CESIUM_ION_TOKEN` in Render's environment settings, then restrict it to your public hostname in Cesium's dashboard. The token is visible to browsers by design.
- The **ASK** bar works by default with a transparent English/Arabic local parser. Do **not** set a payable `ANTHROPIC_API_KEY` on an unrestricted public site. The included public configuration disables API-based LLM calls unless you deliberately override `CLIMAX_ENABLE_PUBLIC_LLM=1` and add your own protections.

## Troubleshooting

- `py is not recognized` → reinstall Python, enable `py` launcher or use `python server.py`.
- `git is not recognized` → install Git and reopen CMD.
- `remote origin already exists` → `git remote set-url origin https://github.com/mnehan67/climax-climate-risk.git`.
- `repository not found` → verify owner, repo name, GitHub sign-in, and repository permissions.
- `failed to push some refs` → you may have initialized the GitHub repo with files; do not force-push. Back up your local work and reconcile the existing remote branch (e.g., clone the repo first) before retrying.
- Map shows no Bing buildings → optional Cesium token missing / blocked; MapLibre fallback still shows local imagery and 3D building footprints.
- Cloud host shows TEST after the real pipeline ran on your laptop → commit/push the **complete** new `data/generated/` folder, then verify the deployment.
