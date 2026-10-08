# Deploying (owner's notes)

How the owner runs the hosted product. Users don't need any of this: they use the site, or run it
on their own computer with `uv run boson-video web`.

The `Dockerfile` runs the site in uploads-only mode (YouTube downloads stay on the user's side).
In Coolify: a new resource from this repo, build pack **Dockerfile**, port **8770**, your domain, a
volume at **`/data`**, and the two keys as environment variables. The first start downloads the
speech models (about 650 MB) and prints your invite code in the logs. To give it a free `*.vercel.app`
address, deploy `deploy/vercel/` on Vercel (its `vercel.json` forwards every request to the
server) and set `BOSON_PUBLIC_URL` on the server to that address.

The server takes uploads only: YouTube downloads stay on the user's side, and YouTube links on the
hosted site wait for the browser extension.
