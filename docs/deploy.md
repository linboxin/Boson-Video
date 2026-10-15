# Deploying the hosted version

How the hosted product is run. Users don't need any of this: they use the site, or run it
on their own computer with `uv run boson-video web`.

The Docker image runs the **Boson engine** on the server: uploads → scenes → speech → OCR →
the document, with optional writing and checking. Users need only a browser. Gemini is not
part of this deployment.

In Coolify, use the existing application (or a new resource from this repo):

- Build pack: **Dockerfile**, application port **8770**, HTTPS domain.
- Persistent volume mounted at **`/data`**. Keep it across deployments; it holds uploads,
  documents, models, invite codes and job inputs.
- One application replica and one Uvicorn process per volume. The queue and invite locks are
  process-local; do not share this volume between independent app processes.
- `BOSON_BUILD_WORKERS=1` initially. Each video already parallelizes speech and frame work.
  Increase only after measuring CPU and memory on the actual server.
- Health check: **GET `/healthz`**, port 8770. The image includes a Docker health check with
  a ten-minute startup allowance for first-time model downloads. Coolify waits its entire
  configured start period before checking: use **10 seconds** on the existing server, where
  the models are already installed, and a longer allowance on a fresh volume.
- Optional environment secrets: `INCEPTION_API_KEY` for summaries, English and terms;
  `TYPESAFE_API_KEY` for semantic checks and the current Ask implementation. Without them,
  the engine still produces scenes, speech and screen text.
- `BOSON_UPLOAD_MAX_MB=2048` by default. Set the ingress upload limit and timeout to support
  the same size; use the direct HTTPS application domain for large uploads.

The first start downloads the speech models (about 650 MB) atomically and prints the owner
invite code in the application logs. Do not put that code or API keys in Git. The models are
reused on subsequent starts. OCR models are bundled with the Python package.

An unfinished upload job is saved in `<video>/job.json` before processing. On startup, unfinished
jobs resume from their saved document. Jobs that failed stay failed; re-upload the same file to
retry. Completed silent videos are not repeatedly transcribed. JSON documents are replaced
atomically so a restart cannot leave a half-written document.

To keep the existing Vercel front address, deploy `deploy/vercel/` and set `BOSON_PUBLIC_URL` to
that address. Its rewrites forward to the Docker server; Vercel does not run the engine. Verify
uploads through that address separately before advertising a size limit there.

The server never contacts YouTube (`--hosted` turns it off everywhere in the engine). A YouTube
video arrives from the user's computer: `uvx boson-video send <link> --to <this site>` makes the
scene map and fetches the sound there, and posts both to `/api/send` with the user's invite code;
the server checks the file, transcribes, writes and checks. Pasting a YouTube link on the hosted
page shows that command. The screen isn't read for these videos (the server has no picture);
the player shows it. A sent video's sound is kept in its folder (about 20 MB an hour), so an
interrupted job resumes after a restart. The send goes through the same upload size limit.

## Verify a deployment

1. Check `/healthz` returns `{"status":"ok"}` over HTTPS.
2. Enter the invite code and upload a short video you own, containing speech and two slides.
3. Check that the job finishes; the player, transcript, scene ribbon, and captured frames work.
   With writer/checker keys configured, also check the summary, English, terms, and Ask.
4. Restart the app during a second upload's processing. The job should resume and finish, and
   the first document and invite should still work.
5. Verify a new YouTube URL is refused without starting a server download, and that the page
   shows the `boson-video send` command.
6. From a computer, run `boson-video send <a short YouTube link> --to <the site> --code <code> --wait`.
   It should report the scene map and the sound, then the server's stages to done; the page plays
   the video with its transcript and summary.

Offline coverage: `uv run pytest`. Build and boot the Docker image on the deployment host;
passing the offline suite alone does not verify the Linux speech models, mounted volume,
proxy upload limits, or paid model connectivity.
