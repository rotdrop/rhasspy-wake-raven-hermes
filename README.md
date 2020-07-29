# Rhasspy Wake Raven Hermes

Implements `hermes/hotword` functionality from [Hermes protocol](https://docs.snips.ai/reference/hermes) using [Rhasspy Raven](https://github.com/rhasspy/raven).

## Requirements

* Python 3.7
* [Rhasspy Raven](https://github.com/rhasspy/raven)

## Installation

```bash
$ git clone https://github.com/rhasspy/rhasspy-wake-raven-hermes
$ cd rhasspy-wake-raven-hermes
$ ./configure
$ make
$ make install
```

## WAV Templates

Steps to record a custom wake word:

1. Record yourself saying the wake word at least 3 times
2. Trim silence around the audio and export 3 WAV files to a directory
    * WAV format should be 16-bit 16Khz mono
3. Pass `--keyword /path/to/directory` to `rhasspy-wake-raven-hermes` with the path to the directory with your WAV templates

You may pass more than one `--keyword` with different WAV directories. It's recommended that you use `--average-templates` to reduce CPU usage.

## Running

```bash
$ bin/rhasspy-wake-raven-hermes <ARGS>
```

## Command-Line Options

```
usage: rhasspy-wake-raven-hermes [-h] [--keyword KEYWORD [KEYWORD ...]]
                                 [--probability-threshold PROBABILITY_THRESHOLD]
                                 [--distance-threshold DISTANCE_THRESHOLD]
                                 [--minimum-matches MINIMUM_MATCHES]
                                 [--refractory-seconds REFRACTORY_SECONDS]
                                 [--window-shift-seconds WINDOW_SHIFT_SECONDS]
                                 [--dtw-window-size DTW_WINDOW_SIZE]
                                 [--vad-sensitivity {1,2,3}]
                                 [--current-threshold CURRENT_THRESHOLD]
                                 [--max-energy MAX_ENERGY]
                                 [--max-current-ratio-threshold MAX_CURRENT_RATIO_THRESHOLD]
                                 [--silence-method {vad_only,ratio_only,current_only,vad_and_ratio,vad_and_current,all}]
                                 [--average-templates]
                                 [--udp-audio UDP_AUDIO UDP_AUDIO UDP_AUDIO]
                                 [--examples-dir EXAMPLES_DIR]
                                 [--examples-format EXAMPLES_FORMAT]
                                 [--log-predictions] [--host HOST]
                                 [--port PORT] [--username USERNAME]
                                 [--password PASSWORD] [--tls]
                                 [--tls-ca-certs TLS_CA_CERTS]
                                 [--tls-certfile TLS_CERTFILE]
                                 [--tls-keyfile TLS_KEYFILE]
                                 [--tls-cert-reqs {CERT_REQUIRED,CERT_OPTIONAL,CERT_NONE}]
                                 [--tls-version TLS_VERSION]
                                 [--tls-ciphers TLS_CIPHERS]
                                 [--site-id SITE_ID] [--debug]
                                 [--log-format LOG_FORMAT]

optional arguments:
  -h, --help            show this help message and exit
  --keyword KEYWORD [KEYWORD ...]
                        Directory with WAV templates and settings (setting-
                        name=value)
  --probability-threshold PROBABILITY_THRESHOLD
                        Probability above which detection occurs (default:
                        0.5)
  --distance-threshold DISTANCE_THRESHOLD
                        Normalized dynamic time warping distance threshold for
                        template matching (default: 0.22)
  --minimum-matches MINIMUM_MATCHES
                        Number of templates that must match to produce output
                        (default: 1)
  --refractory-seconds REFRACTORY_SECONDS
                        Seconds before wake word can be activated again
                        (default: 2)
  --window-shift-seconds WINDOW_SHIFT_SECONDS
                        Seconds to shift sliding time window on audio buffer
                        (default: 0.02)
  --dtw-window-size DTW_WINDOW_SIZE
                        Size of band around slanted diagonal during dynamic
                        time warping calculation (default: 5)
  --vad-sensitivity {1,2,3}
                        Webrtcvad VAD sensitivity (1-3)
  --current-threshold CURRENT_THRESHOLD
                        Debiased energy threshold of current audio frame
  --max-energy MAX_ENERGY
                        Fixed maximum energy for ratio calculation (default:
                        observed)
  --max-current-ratio-threshold MAX_CURRENT_RATIO_THRESHOLD
                        Threshold of ratio between max energy and current
                        audio frame
  --silence-method {vad_only,ratio_only,current_only,vad_and_ratio,vad_and_current,all}
                        Method for detecting silence
  --average-templates   Average wakeword templates together to reduce number
                        of calculations
  --udp-audio UDP_AUDIO UDP_AUDIO UDP_AUDIO
                        Host/port/siteId for UDP audio input
  --examples-dir EXAMPLES_DIR
                        Save positive example audio to directory as WAV files
  --examples-format EXAMPLES_FORMAT
                        Format of positive example WAV file names using
                        strftime (relative to examples-dir)
  --log-predictions     Log prediction probabilities for each audio chunk
                        (very verbose)
  --host HOST           MQTT host (default: localhost)
  --port PORT           MQTT port (default: 1883)
  --username USERNAME   MQTT username
  --password PASSWORD   MQTT password
  --tls                 Enable MQTT TLS
  --tls-ca-certs TLS_CA_CERTS
                        MQTT TLS Certificate Authority certificate files
  --tls-certfile TLS_CERTFILE
                        MQTT TLS client certificate file (PEM)
  --tls-keyfile TLS_KEYFILE
                        MQTT TLS client key file (PEM)
  --tls-cert-reqs {CERT_REQUIRED,CERT_OPTIONAL,CERT_NONE}
                        MQTT TLS certificate requirements for broker (default:
                        CERT_REQUIRED)
  --tls-version TLS_VERSION
                        MQTT TLS version (default: highest)
  --tls-ciphers TLS_CIPHERS
                        MQTT TLS ciphers to use
  --site-id SITE_ID     Hermes site id(s) to listen for (default: all)
  --debug               Print DEBUG messages to the console
  --log-format LOG_FORMAT
                        Python logger format
```
