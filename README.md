# Slay the Spire 2 desktop launcher

**English** · [简体中文](README.zh-CN.md)

A Windows desktop launcher for [sts2-cli](https://github.com/wuhao21/sts2-cli). Play manually or let a DeepSeek or Claude persona play, then review each room of the run. Play uses your local Steam game engine, with actions and game state shown in the game terminal.

## Download and play

**[Download the Windows x64 portable ZIP](https://github.com/fallingstars123/sts2-cli/releases/latest/download/sts2-cli-windows-x64.zip)**

1. Install **Slay the Spire 2** through Steam and download the ZIP.
2. Extract the entire ZIP into a writable folder and double-click `Start STS2.cmd`.
3. Choose **Manual** or **AI play** and select **Start run**. On the first run, the launcher locates your Steam game automatically. If it asks for a folder, select the installed game folder.

The ZIP includes Python and .NET. Manual play needs no API key. For AI play, save your provider key in **API settings** under the gear menu and select a model in **Persona panel**. The launcher can download the provider's Python client on first use, which requires an internet connection.

![English launcher showing the selected AI persona, speaking language, and model](docs/screenshots/launcher-en.png)

## Features

- **Personas and languages.** Save a model, speaking style, and output language per persona. The interface and AI commentary each offer 17 languages and can be set independently.
- **Local saves.** Detect or set a save folder from the gear menu, then select a save on the launch page.
- **AI chat and run history.** Expand either view from the sidebar. Each run has its own archive, with separate folders for encounters, chests, rest sites, and other rooms.
- **Run maps.** Switch between runs and acts. The scrollable map uses the engine's grid and room connections, with bright dots marking the traveled route. Select a visited room to open its record.
- **Game icons.** Room and character icons are read from your Steam install. Archives can still be opened with built-in symbols when the art is unavailable.
- **Character and run analysis.** The top panel shows the portrait, current HP, and recent health changes. Expand Deck or Relics to see their current contents with icons and quantities. Historical charts appear below.

## Screenshots

The conversations, runs, and statistics below use sample data.

![Run analysis with the character, health bar, and recent HP at the top and historical charts below](docs/screenshots/analysis-en.png)

![Run map showing alternate branches, room icons, and the route already taken](docs/screenshots/map-en.png)

![AI chat showing persona commentary and the associated game actions](docs/screenshots/chat-en.png)

## Docs and license

- [Desktop launcher guide](docs/desktop-launcher.md)
- [Command-line play, source builds, and JSON protocol](docs/cli.md)
- [Release notes and downloads](https://github.com/fallingstars123/sts2-cli/releases)

This fork builds on [wuhao21/sts2-cli](https://github.com/wuhao21/sts2-cli) and is distributed under the [MIT license](LICENSE).
