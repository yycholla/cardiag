# cardiag on Even G2 glasses

An [Even Hub](https://hub.evenrealities.com) app: a web page that runs inside
the Even Realities phone app, asks cardiag for its latest values, and shows six
of them at a time on the glasses.

```
car -> adapter -> cardiag (the box in the car) <- phone (Even Realities app) -> glasses
                          GET /api/glance, twice a second          Bluetooth
```

The built app is kept in `../src/cardiag/web/glasses`, inside the Python
package, so every cardiag serves it at `/glasses/` and the box's updater
carries it. After changing anything here, build again and commit the result:

```sh
npm install
npm test          # what each cell and the top line say
npm run build     # into ../src/cardiag/web/glasses
```

## Try it without glasses

```sh
../.venv/bin/cardiag --sim focus_dct serve      # in one terminal
npm run sim                                     # Even's simulator, in another
```

`http://127.0.0.1:8000/glasses/` in a browser shows the same thing as a preview.

## On the glasses, straight from the box

With Developer Mode on in the phone app, and the phone able to reach the box:

```sh
npx evenhub qr --url "http://<the box's address>:8000/glasses/"
```

Scan the code from the Even Hub tab. The page comes from the box, so it asks
the box for values and nothing needs configuring. This way of running an app
stops when the phone locks or the phone app goes to the background; scan again
to bring it back.

## Installed, as a private or beta build

An installed app may only reach the addresses its manifest lists, and the list
takes whole addresses, no wildcards. So a build is made for one cardiag, by
one or more of its addresses:

```sh
npm run pack -- https://carbox.your-tailnet.ts.net
npx evenhub create cardiag.ehpk        # the first time
npx evenhub upload cardiag.ehpk -m "what changed"    # after that
npx evenhub promote <version>          # to start it from the glasses menu
```

The addresses are written into the manifest and into a `config.json` beside
the page, so nothing is typed on the phone; the app asks each in turn until one
answers. `--id com.yourname.cardiag` sets the package id, which has to be one
nobody else has taken.

Put an `https` address first. Even's documentation says plain `http` is only for
development, and the phone may refuse it from an installed app. On a tailnet,
`tailscale serve --bg 8000` on the box gives it one.

## What is and is not checked

The texts are tested with Node. The app was run in Even's simulator (0.9.5)
against the simulated geared Focus: the pages, turning them, and leaving. The
simulator is not the hardware: how fast the glasses take seven pieces of text
over Bluetooth, and whether presses arrive the way the simulator sends them,
are only known once it has run on glasses.
