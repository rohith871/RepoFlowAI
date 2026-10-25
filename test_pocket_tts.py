from pocket_tts import TTSModel
from scipy.io.wavfile import write

def main():
    print("Loading Pocket TTS model...")
    model = TTSModel.load_model()

    print("Loading voice...")
    voice = model.get_state_for_audio_prompt("alba")

    text = """
    Welcome to RepoFlow AI!
    Today, we will explore a codebase,
    understand its architecture,
    and discover how its components work together.
    """

    print("Generating speech...")
    audio = model.generate_audio(voice, text)

    output_file = "pocket_tts_test.wav"

    write(
        output_file,
        model.sample_rate,
        audio.numpy()
    )

    duration = audio.shape[-1] / model.sample_rate

    print(f"\nSuccess! Audio saved to: {output_file}")
    print(f"Duration: {duration:.2f} seconds")

if __name__ == "__main__":
    main()
