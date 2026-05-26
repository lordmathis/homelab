import threading
import time

from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini.utils import create_head_pose

from voice_assistant.wake_word import WakeWordDetector
from voice_assistant.vad import VoiceActivityDetector


class VoiceAssistantApp(ReachyMiniApp):
    custom_app_url: str | None = "http://0.0.0.0:8042"
    request_media_backend: str | None = None

    def __init__(self):
        super().__init__()
        self._wake_word = None
        self._reachy = None
        self._conversation_thread = None
        self._stop_event = threading.Event()

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        print("[main] run() called, starting wake word detector...")
        self._reachy = reachy_mini
        self._stop_event = stop_event

        self._wake_word = WakeWordDetector(
            reachy_mini,
            on_detected=self._on_wake_word,
            threshold=0.7,
        )
        self._wake_word.start()
        print("[main] Wake word detector started, say 'Hey Reachy!'")

        while not stop_event.is_set():
            time.sleep(0.1)

        self._wake_word.stop()

    def _on_wake_word(self):
        if self._conversation_thread and self._conversation_thread.is_alive():
            print("[main] Already in conversation, ignoring wake word")
            return

        self._conversation_thread = threading.Thread(
            target=self._run_conversation, daemon=True
        )
        self._conversation_thread.start()

    def _run_conversation(self):
        self._reachy.goto_target(
            head=create_head_pose(z=10, mm=True),
            antennas=[0.3, -0.3],
            duration=0.5,
        )
        print("[conversation] Listening...")

        last_speech_time = time.time()
        conversation_timeout = 10.0

        while not self._stop_event.is_set():
            vad = VoiceActivityDetector(
                energy_threshold=0.02,
                end_of_utterance_silence=1.5,
                conversation_timeout=9999.0,
                min_speech_duration=0.3,
            )

            while not self._stop_event.is_set():
                if time.time() - last_speech_time > conversation_timeout:
                    print("[conversation] No speech for 10s, ending conversation")
                    self._reachy.goto_target(
                        head=create_head_pose(),
                        antennas=[0, 0],
                        duration=0.5,
                    )
                    return

                sample = self._reachy.media.get_audio_sample()
                if sample is None:
                    time.sleep(0.01)
                    continue

                result = vad.process_frame(sample)

                if result["end_of_utterance"]:
                    print(f"[conversation] End of utterance (speech: {result['speech_duration']:.1f}s)")
                    last_speech_time = time.time()
                    break

            print("[conversation] Listening again...")

    def stop(self):
        if self._wake_word:
            self._wake_word.stop()
        super().stop()


if __name__ == "__main__":
    app = VoiceAssistantApp()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
