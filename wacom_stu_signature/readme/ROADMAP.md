- The widget is registered globally under the `signature` name, so every form
  that uses that widget opens the Wacom dialog first. Restricting it to some
  models, or making it an option of the widget, would make it less intrusive.
- Only the first connected pad is used.
- Pen pressure is not used: strokes have a constant width.
- Add JavaScript (Hoot) tests with a mocked SigCaptX service.
