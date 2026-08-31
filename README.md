# discord-webhook-gui

Little desktop app I put together for sending stuff through Discord webhooks without
having to mess with curl commands or Postman every time. Started as just a way to
send a message with formatting and grew from there.

## Why

Got tired of doing this:

```
curl -X POST -H "Content-Type: application/json" -d '{"content":"hello"}' <webhook url>
```

every time I wanted to post something, especially with files attached. Wanted
something with buttons.

## Setup

```
pip install requests
python discord_webhook_gui.py
```

That's the minimum. Two more things are optional but worth having:

```
pip install pillow        # lets you paste screenshots straight in as attachments
pip install tkinterdnd2   # lets you drag files onto the window instead of browsing
```

Without those two it still works fine, just a bit more manual (use the Add Files
button, and clipboard paste only handles text/links).

If you're on Linux and tkinter isn't already there:
```
sudo apt install python3-tk
```

## Getting a webhook URL

Server settings -> Integrations -> Webhooks -> New Webhook -> copy the URL.
Paste it into the box at the top, hit "Save as..." to keep it around under a name
so you don't have to paste it again next time.

## What's in it

- formatting buttons for bold/italic/underline/strikethrough/code/spoiler/quote,
  they just wrap whatever you've got selected in the right markdown
- select some text, paste a link over it (ctrl+v with a URL on your clipboard),
  turns into `[that text](the link)` automatically
- paste a screenshot and it attaches it as a file instead of dumping garbage into
  the text box
- drag files onto the window to attach them
- emoji button + an @ button for inserting user/role/channel mentions or @everyone/@here
  without having to remember the `<@id>` syntax
- messages over 2000 chars get split into multiple sends automatically (can turn
  this off if you'd rather it just refuse to send)
- can save more than one webhook and blast the same message out to all of them at once
- basic embed support - title, description, a color

## Notes to self

- webhook URLs are stored in `~/.discord_webhook_gui_config.json`, plaintext, so
  don't commit that file or hand the laptop to anyone sketchy
- broadcast mode sends one request at a time with a short delay between each,
  not parallel, so sending to a bunch of servers takes a few seconds - that's
  on purpose so discord doesn't rate limit it
- the "unusual URL" popup is just a sanity check in case I fat-finger the
  wrong link in, can ignore it if it's actually fine

## Todo (maybe)

- message templates so I don't retype the same announcement every time
- scheduled sends
- some kind of send history/log
