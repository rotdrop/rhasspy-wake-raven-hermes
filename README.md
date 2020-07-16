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

## Running

```bash
$ bin/rhasspy-wake-raven-hermes <ARGS>
```

## Command-Line Options

```
usage: rhasspy-wake-raven-hermes [-h] --template-dir TEMPLATE_DIR
                                 --distance-threshold DISTANCE_THRESHOLD
                                 [--wakeword-id WAKEWORD_ID]
                                 [--udp-audio UDP_AUDIO UDP_AUDIO UDP_AUDIO]
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
  --template-dir TEMPLATE_DIR
                        Directories with Raven WAV templates
  --distance-threshold DISTANCE_THRESHOLD
                        Normalized dynamic time warping distance threshold for
                        template matching
  --wakeword-id WAKEWORD_ID
                        Wakeword ID for model (default: use file name)
  --udp-audio UDP_AUDIO UDP_AUDIO UDP_AUDIO
                        Host/port/siteId for UDP audio input
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
