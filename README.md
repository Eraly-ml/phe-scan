# PHE Scan

Experimental electronic stethoscope: a MAX9814 microphone module sends an analog signal to an ESP32, and a desktop app plays and visualizes the filtered audio.

**Research / learning prototype, not a medical device.** It does not diagnose disease or determine sinus rhythm; the display is a sound waveform, not an ECG. Filters and automatic gain can change the signal. Sound acquisition, sampling timing and clinical usefulness have not been validated.

## Hardware

- Original ESP32 (tested with ESP32-D0WD-V3 and 4 MB flash), USB data cable, and MAX9814 module.
- MAX9814 `VDD` → ESP32 `3V3`; `GND` → `GND`; `OUT` → `GPIO34` (ADC1). Confirm your board labels before connecting. Use 3.3 V, not 5 V, for the microphone supply.
- A compatible USB-to-serial driver, such as [Silicon Labs CP210x VCP](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers), may be needed on Windows.
- The acoustic tubing and stethoscope membrane need to be mechanically coupled to the microphone.

## Setup (Windows)

1. Install Python 3.11–3.13 including the Python launcher and Tcl/Tk. Download or clone this repository.
2. Run `setup.bat` once. It creates a local virtual environment and installs dependencies.
3. Flash MicroPython if it is not already installed, as described below. Flashing overwrites existing firmware. Back up anything important first.
4. Run `start.bat`. Connect the ESP32, click **Обновить**, select the COM port and click **Подключить**. Use headphones and start at low volume.

The app is in Russian. Controls: amplification, upper filter frequency, noise gate, optional 50 Hz notch and heart / breathing presets. The plot shows approximately five seconds of filtered sound. The 50 Hz notch and aggressive noise gate can also remove useful sounds. This prototype does not record WAV or detect anomalies.

Alternatively, run `python -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.txt`, then `.venv\Scripts\python stetho.py`. On non-Windows systems install Python/Tk and PortAudio, create a virtual environment, install the same dependencies and run `python stetho.py`; these platforms have not been tested.

## Flashing the ESP32

The `firmware/` folder contains the official **MicroPython ESP32_GENERIC v1.29.0**, sourced from [micropython.org](https://micropython.org/download/ESP32_GENERIC/). It is third-party firmware, not PHE Scan's own firmware. The app sends its sampling program to MicroPython's serial REPL on each connection; the sampling program is contained in `stetho.py`. This binary is for the classic ESP32, not ESP32-S3 or C3.

Close applications using the COM port. After `setup.bat`, substitute your port for `COM6`:

```powershell
.venv\Scripts\python -m esptool --port COM6 --baud 115200 write-flash 0x1000 firmware\ESP32_GENERIC-20260824-v1.29.0.bin
```

If MicroPython reports a corrupt filesystem because the board previously had another firmware, perform a full erase and then run the write command above again. **Full erase permanently removes all flash contents**, including files and settings:

```powershell
.venv\Scripts\python -m esptool --port COM6 erase-flash
```

MicroPython is distributed under the [MIT license](https://github.com/micropython/micropython/blob/v1.29.0/LICENSE); its firmware includes third-party components with their own notices, available in the [MicroPython source tree](https://github.com/micropython/micropython/tree/v1.29.0).

## Limitations and troubleshooting

- This is an early prototype: MicroPython samples at a target 4 kHz over the REPL and USB. Timing, audio fidelity and latency are not guaranteed; the stream uses 8-bit samples. Original ESP32 ADC and MAX9814 AGC can add noise or distortion.
- If no port appears, reconnect the board, install the appropriate USB driver and press **Обновить**. If COM is busy, close serial monitors. If the ESP32 fails to respond, press its EN/RST button and retry.
- Compare quiet surroundings, firmly held tubing and different filter settings. Avoid interpreting this as a calibrated diagnostic recording.
- Do not upload personal recordings or full board flash backups to a public repository.
