# KeiFrame

[简体中文](README.zh-CN.md)

[![Deep Dive on zread](https://img.shields.io/badge/zread-Technical%20Notes-blue)](https://zread.ai/Archer-Ucx0DSe4f57t9/Keiframe)  

[![License](https://img.shields.io/github/license/Archer-Ucx0DSe4f57t9/keiframe)](https://github.com/Archer-Ucx0DSe4f57t9/keiframe/blob/main/LICENSE)


KeiFrame is a timeline-driven event reminder engine for StarCraft II Co-op missions.

This repository contains the developer-focused source version of the project.  
End-user distributions and usage documentation are maintained separately at https://www.kdocs.cn/l/cvCj6uEth9os (simplified Chinese only).

Maintained by Archer

---

## Overview

KeiFrame evolved from `sc2timer` with structural refactoring and extended event handling.

The project focuses on:

- Timeline abstraction
- Event-driven reminder logic
- Configurable rendering layer
- Audio notification pipeline
- Extensible data definitions

The software does NOT modify game files, inject processes, or access protected resources.

---

## Architecture

### Timeline Engine
- SQLite-based time definitions
- Countdown lifecycle management
- Event dispatch system

### Presentation Layer
- GUI configuration
- Font and color customization
- Overlay message rendering

### Audio Layer
- Custom audio playback
- Event-trigger mapping

All mission data is decoupled from core engine logic.

---

## Project Structure

For specific functionalities of different project modules, we recommend clicking the zread link at the top. However, please note that zread contains numerous inaccuracies regarding the game's specific features.
```

Keiframe/
├── src/                              │   ├── main.py                       # Application entry point
│   ├── config.py                     # Central configuration (overridden by settings.json)
│   ├── config_hotkeys.py             # Hotkey binding configuration
│   ├── qt_gui.py                     # Main Qt window and signal/slot connections
│   ├── control_window.py             # Lock/unlock control panel
│   ├── game_state_service.py         # Game state monitoring via port 6119
│   ├── game_time_handler.py          # Time flow management
│   ├── language_manager.py           # Multi-language support (EN/ZH)
│   ├── memo_overlay.py               # Map notes overlay with animations
│   ├── countdown_manager.py          # Concurrent timer management
│   ├── db/                           # Database layer
│   │   ├── db_manager.py             # SQLite connection management
│   │   ├── daos.py                   # Data Access Objects base classes
│   │   ├── map_daos.py               # Map data operations
│   │   ├── mutator_daos.py           # Mutator data operations
│   │   └── enemy_comp_daos.py        # Enemy composition data operations
│   ├── map_handlers/                 # Map identification and event management
│   │   ├── map_processor.py          # Map template loader and processor
│   │   ├── IdentifyMap.py            # Map identification logic
│   │   ├── map_event_manager.py      # Generic map event scheduling
│   │   ├── map_loader.py             # Map configuration loading
│   │   ├── malwarfare_map_handler.py # Image recognition module for Malwarfare
│   │   ├── malwarfare_event_manager.py # Malwarfare-specific events manager
│   │   └── malwarfate_ocr_processor.py # OCR text recognition processor for Malwarfare
│   ├── mutaor_handlers/              # Mutator and race recognition
│   │   ├── mutator_and_enemy_race_recognizer.py # Template matching recognizer
│   │   └── mutator_manager.py        # Mutator data management
│   ├── output/                       # Output and presentation layer
│   │   ├── message_presenter.py      # Alert text rendering with outlines
│   │   ├── toast_manager.py          # Toast notification management
│   │   └── sound_player.py           # Audio playback system
│   ├── settings_window/              # Configuration UI
│   │   ├── settings_window.py        # Main settings dialog
│   │   ├── tabs.py                   # Settings tab organization
│   │   ├── widgets.py                # Custom UI widgets
│   │   ├── setting_data_handler.py   # Settings data management
│   │   └── complex_inputs.py         # Complex input components
│   ├── ui_setup.py                   # UI initialization helpers
│   ├── app_window_manager.py         # Window management utilities
│   ├── tray_manager.py               # System tray icon and menu
│   ├── troop_util.py                 # Troop-related utilities
│   └── utils/                        # Utility modules
│       ├── fileutil.py               # File path operations
│       ├── logging_util.py           # Logging configuration
│       ├── math_utils.py             # Mathematical calculations
│       ├── font_uitils.py            # Font loading and management
│       ├── window_utils.py           # Window positioning utilities
│       ├── data_validator.py         # Data validation helpers
│       ├── debug_utils.py            # Debug utilities
│       └── excel_utils.py            # Excel file operations
├── resources/                        # Runtime resources
│   ├── db/                           # SQLite database files
│   │   ├── maps.db                   # Map data database
│   │   ├── mutators.db               # Mutator data database
│   │   ├── enemies.db                # Enemy composition database
│   │   └── db_backups/               # Database backup files
│   ├── enemy_comps/                  # Enemy composition CSV files
│   ├── templates/                    # Recognition templates
│   │   ├── en_blue/ en_green/ en_orange/ en_yellow/
│   │   ├── zh_blue/ zh_green/ zh_orange/ zh_yellow/
│   │   ├── races/                    # Race icon templates
│   │   └── mutators/                 # Mutator icon templates
│   ├── icons/                        # Application icons
│   ├── fonts/                        # Custom font files
│   ├── sounds/                       # Alert sound files
│   ├── memo/                         # Map note images
│   └── troops/                       # Troop icon resources
├── python/                           # Embedded Python environment
├── requirements.txt                  # Python dependencies
├── settings.json                     # User settings override
└── build-keiframe.bat                # Windows build script


```

---

## Development Setup

```bash
git clone https://github.com/<your-github>/keiframe.git
cd keiframe

python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

python -m src.main

```

----------

## Port (6119)

Default listening port: `6119`

If binding fails:

-   Ensure the port is not occupied
    
-   Run the following commands` (Windows, admin required)
    ```bash
    stop winnat
    netsh int ipv4 add excludedportrange protocol=tcp startport=6119 numberofports=1
	net start winnat
    ```
----------

## Contributing

-   Keep mission data separate from engine logic
    
-   Avoid hardcoded behavior
    
-   Maintain modular structure
    
-   Open an issue before major refactoring
    

----------

## License

MIT License

See `LICENSE` for details.

----------

## Credits

Originally based on `sc2timer`https://github.com/ylkangpeter/sc2-expo

Refactored and maintained by Archer.