# Vox

Vox is a local voice input layer: it turns the user's speech into text and delivers that text to wherever they are working.

## Language

### Listening modes

**Push-to-talk**:
The listening mode where speech is captured only while the user holds the hotkey; releasing it ends the utterance.
_Avoid_: PTT mode, hold mode

**Continuous dictation**:
The listening mode toggled on and off with its own hotkey, where the user speaks freely and each utterance is committed on Pause without holding a key.
_Avoid_: Continual dictation, hands-free mode, always-on, open mic

### Speech and text

**Utterance**:
One contiguous chunk of the user's speech that becomes one piece of delivered text.
_Avoid_: Segment, clip, recording

**Pause**:
A stretch of silence long enough to end an utterance during continuous dictation.
_Avoid_: Gap, timeout

**Commit**:
The moment an utterance is finalised and its text is delivered to the focused window.
_Avoid_: Flush, send, submit

**Injection**:
Delivering committed text to the user, via the clipboard, a paste, or typing into the focused window.
_Avoid_: Output, insertion
