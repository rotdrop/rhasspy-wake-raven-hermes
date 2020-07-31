"""Hermes MQTT server for Rhasspy wakeword with Raven"""
import asyncio
import logging
import queue
import re
import socket
import threading
import time
import typing
from pathlib import Path

from rhasspyhermes.audioserver import AudioFrame
from rhasspyhermes.base import Message
from rhasspyhermes.client import GeneratorType, HermesClient, TopicArgs
from rhasspyhermes.wake import (
    GetHotwords,
    Hotword,
    HotwordDetected,
    HotwordError,
    HotwordExampleRecorded,
    Hotwords,
    HotwordToggleOff,
    HotwordToggleOn,
    HotwordToggleReason,
    RecordHotwordExample,
)
from rhasspysilence import WebRtcVadRecorder
from rhasspywake_raven import Raven
from rhasspywake_raven.utils import trim_silence

WAV_HEADER_BYTES = 44
_LOGGER = logging.getLogger("rhasspywake_raven_hermes")

# -----------------------------------------------------------------------------


class WakeHermesMqtt(HermesClient):
    """Hermes MQTT server for Rhasspy wakeword with Raven."""

    def __init__(
        self,
        client,
        ravens: typing.List[Raven],
        examples_dir: typing.Optional[Path] = None,
        examples_format: str = "{keyword}/examples/%Y%m%d-%H%M%S.wav",
        wakeword_id: str = "",
        site_ids: typing.Optional[typing.List[str]] = None,
        enabled: bool = True,
        sample_rate: int = 16000,
        sample_width: int = 2,
        channels: int = 1,
        chunk_size: int = 1920,
        udp_audio: typing.Optional[typing.List[typing.Tuple[str, int, str]]] = None,
        udp_chunk_size: int = 2048,
        log_predictions: bool = False,
    ):
        super().__init__(
            "rhasspywake_raven_hermes",
            client,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
            site_ids=site_ids,
        )

        self.subscribe(
            AudioFrame,
            HotwordToggleOn,
            HotwordToggleOff,
            GetHotwords,
            RecordHotwordExample,
        )

        self.ravens = ravens
        self.wakeword_id = wakeword_id

        self.examples_dir = examples_dir
        self.examples_format = examples_format

        self.enabled = enabled
        self.disabled_reasons: typing.Set[str] = set()

        # Required audio format
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels

        self.chunk_size = chunk_size

        # Queue of WAV audio chunks to process (plus site_id)
        self.wav_queue: queue.Queue = queue.Queue()

        self.first_audio: bool = True

        self.last_audio_site_id: str = "default"

        # Fields for recording examples
        self.recording_example = False
        self.example_recorder = WebRtcVadRecorder(max_seconds=10)
        self.example_future: typing.Optional[asyncio.Future] = None

        # Raw audio chunk queues for Raven threads
        self.chunk_queues: typing.List[queue.Queue] = [
            queue.Queue() for raven in ravens
        ]

        # Start main thread to convert audio from MQTT/UDP
        self.audio_thread = threading.Thread(target=self.audio_thread_proc, daemon=True)
        self.audio_thread.start()

        # Start a thread per Raven instance (per-keyword)
        self.detection_threads = [
            threading.Thread(
                target=self.detection_thread_proc,
                args=(self.chunk_queues[i], self.ravens[i]),
                daemon=True,
            )
            for i in range(len(self.ravens))
        ]

        for thread in self.detection_threads:
            thread.start()

        # Listen for raw audio on UDP too
        self.udp_chunk_size = udp_chunk_size

        if udp_audio:
            for udp_host, udp_port, udp_site_id in udp_audio:
                threading.Thread(
                    target=self.udp_thread_proc,
                    args=(udp_host, udp_port, udp_site_id),
                    daemon=True,
                ).start()

    # -------------------------------------------------------------------------

    async def handle_audio_frame(
        self, wav_bytes: bytes, site_id: str = "default"
    ) -> None:
        """Process a single audio frame"""
        self.wav_queue.put((wav_bytes, site_id))

    async def handle_detection(
        self, matching_indexes: typing.List[int], raven: Raven
    ) -> typing.AsyncIterable[
        typing.Union[typing.Tuple[HotwordDetected, TopicArgs], HotwordError]
    ]:
        """Handle a successful hotword detection"""
        try:
            template = raven.templates[matching_indexes[0]]

            wakeword_id = raven.keyword_name or template.name
            if not wakeword_id:
                wakeword_id = "default"

            yield (
                HotwordDetected(
                    site_id=self.last_audio_site_id,
                    model_id=template.name,
                    current_sensitivity=raven.probability_threshold,
                    model_version="",
                    model_type="personal",
                ),
                {"wakeword_id": wakeword_id},
            )
        except Exception as e:
            _LOGGER.exception("handle_detection")
            yield HotwordError(
                error=str(e),
                context=f"{raven.keyword_name}: {template.name}",
                site_id=self.last_audio_site_id,
            )

    async def handle_get_hotwords(
        self, get_hotwords: GetHotwords
    ) -> typing.AsyncIterable[typing.Union[Hotwords, HotwordError]]:
        """Report available hotwords"""
        try:
            models: typing.List[Hotword] = []

            # Each keyword is in a separate Raven instance
            for raven in self.ravens:
                # Assume that the directory name is something like
                # "okay-rhasspy" for the keyword "okay rhasspy".
                models.append(
                    Hotword(
                        model_id=raven.keyword_name,
                        model_words=re.sub(r"[_-]+", " ", raven.keyword_name),
                    )
                )

            yield Hotwords(
                models=models, id=get_hotwords.id, site_id=get_hotwords.site_id
            )

        except Exception as e:
            _LOGGER.exception("handle_get_hotwords")
            yield HotwordError(
                error=str(e), context=str(get_hotwords), site_id=get_hotwords.site_id
            )

    async def handle_record_example(
        self, record_example: RecordHotwordExample
    ) -> typing.AsyncIterable[
        typing.Union[typing.Tuple[HotwordExampleRecorded, TopicArgs], HotwordError]
    ]:
        """Record an example of a hotword."""
        try:
            assert (
                not self.recording_example
            ), "Only one example can be recorded at a time"

            # Start recording
            assert self.loop, "No loop"
            self.example_future = self.loop.create_future()
            self.example_recorder.start()
            self.recording_example = True

            # Wait for result
            _LOGGER.debug("Recording example (id=%s)", record_example.id)
            example_audio = await self.example_future
            assert isinstance(example_audio, bytes)

            # Trim silence
            _LOGGER.debug("Trimming silence from example")
            example_audio = trim_silence(example_audio)

            # Convert to WAV format
            wav_data = self.to_wav_bytes(example_audio)

            yield (
                HotwordExampleRecorded(wav_bytes=wav_data),
                {"site_id": record_example.site_id, "request_id": record_example.id},
            )

        except Exception as e:
            _LOGGER.exception("handle_record_example")
            yield HotwordError(
                error=str(e),
                context=str(record_example),
                site_id=record_example.site_id,
            )

    def add_example_audio(self, audio_data: bytes):
        """Add an audio frame to the currently recording example."""
        result = self.example_recorder.process_chunk(audio_data)
        if result:
            self.recording_example = False
            assert self.example_future is not None, "No future"
            example_audio = self.example_recorder.stop()
            _LOGGER.debug(
                "Recorded %s byte(s) for audio for example", len(example_audio)
            )

            # Signal waiting coroutine with audio
            assert self.loop, "No loop"
            self.loop.call_soon_threadsafe(
                self.example_future.set_result, example_audio
            )

    # -------------------------------------------------------------------------

    def audio_thread_proc(self):
        """Handle WAV audio chunks."""
        try:
            while True:
                wav_bytes, site_id = self.wav_queue.get()
                if wav_bytes is None:
                    # Shutdown signal
                    for chunk_queue in self.chunk_queues:
                        chunk_queue.put(None)

                    # Wait for detection threads to exit
                    for thread in self.detection_threads:
                        thread.join()

                    break

                self.last_audio_site_id = site_id

                # Handle audio frames
                if self.first_audio:
                    _LOGGER.debug("Receiving audio")
                    self.first_audio = False

                # Extract/convert audio data
                audio_data = self.maybe_convert_wav(wav_bytes)

                if self.recording_example:
                    # Add to currently recording example
                    self.add_example_audio(audio_data)

                    # Don't process audio for wake word while recording
                    continue

                # Add to queues for detection threads
                for chunk_queue in self.chunk_queues:
                    chunk_queue.put(audio_data)
        except Exception:
            _LOGGER.exception("audio_thread_proc")

    def detection_thread_proc(self, chunk_queue: queue.Queue, raven: Raven):
        """Run Raven detection on audio chunks."""
        try:
            _LOGGER.debug("Listening for keyword %s", raven.keyword_name)

            while True:
                audio_data = chunk_queue.get()
                if audio_data is None:
                    # Shutdown signal
                    break

                if audio_data:
                    try:
                        keep_audio = bool(self.examples_dir)
                        matching_indexes = raven.process_chunk(
                            audio_data, keep_audio=keep_audio
                        )
                        if len(matching_indexes) >= raven.minimum_matches:
                            # Report detection
                            assert self.loop is not None, "No loop"
                            asyncio.run_coroutine_threadsafe(
                                self.publish_all(
                                    self.handle_detection(matching_indexes, raven)
                                ),
                                self.loop,
                            )

                            if keep_audio:
                                # Save positive example
                                assert self.examples_dir is not None
                                example_path = self.examples_dir / time.strftime(
                                    self.examples_format
                                ).format(keyword=raven.keyword_name)

                                example_path.parent.mkdir(parents=True, exist_ok=True)

                                with open(example_path, "wb") as example_file:
                                    example_wav_bytes = self.to_wav_bytes(
                                        raven.example_audio_buffer
                                    )
                                    example_file.write(example_wav_bytes)

                                _LOGGER.debug("Wrote example to %s", example_path)
                    except Exception:
                        _LOGGER.exception("process_chunk")
        except Exception:
            _LOGGER.exception("detection_thread_proc")

    # -------------------------------------------------------------------------

    def stop(self):
        """Stop audio and detection threads."""
        self.wav_queue.put((None, ""))

        _LOGGER.debug("Waiting for detection threads to stop...")
        self.audio_thread.join()

    # -------------------------------------------------------------------------

    def udp_thread_proc(self, host: str, port: int, site_id: str):
        """Handle WAV chunks from UDP socket."""
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind((host, port))
            _LOGGER.debug("Listening for audio on UDP %s:%s", host, port)

            while True:
                wav_bytes, _ = udp_socket.recvfrom(
                    self.udp_chunk_size + WAV_HEADER_BYTES
                )

                if self.enabled:
                    self.wav_queue.put((wav_bytes, site_id))
        except Exception:
            _LOGGER.exception("udp_thread_proc")

    # -------------------------------------------------------------------------

    async def on_message_blocking(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ) -> GeneratorType:
        """Received message from MQTT broker."""
        # Check enable/disable messages
        if isinstance(message, HotwordToggleOn):
            if message.reason == HotwordToggleReason.UNKNOWN:
                # Always enable on unknown
                self.disabled_reasons.clear()
            else:
                self.disabled_reasons.discard(message.reason)

            if self.disabled_reasons:
                _LOGGER.debug("Still disabled: %s", self.disabled_reasons)
            else:
                self.enabled = True
                self.first_audio = True
                _LOGGER.debug("Enabled")
        elif isinstance(message, HotwordToggleOff):
            self.enabled = False
            self.disabled_reasons.add(message.reason)
            _LOGGER.debug("Disabled")
        elif isinstance(message, AudioFrame):
            if self.enabled:
                assert site_id, "Missing site_id"
                await self.handle_audio_frame(message.wav_bytes, site_id=site_id)
        elif isinstance(message, GetHotwords):
            async for hotword_result in self.handle_get_hotwords(message):
                yield hotword_result
        elif isinstance(message, RecordHotwordExample):
            # Handled in on_message
            pass
        else:
            _LOGGER.warning("Unexpected message: %s", message)

    async def on_message(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ) -> GeneratorType:
        """Received message from MQTT broker (non-blocking)."""
        if isinstance(message, RecordHotwordExample):
            async for example_result in self.handle_record_example(message):
                yield example_result
