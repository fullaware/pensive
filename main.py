"""Main entry point for Pensive Family Assistant - launches Gradio app."""

# This file is kept for backward compatibility
# The main application is now in gradio_app.py

if __name__ in {"__main__", "__mp_main__"}:
    from gradio_app import build_gradio_app
    import os
    
    app = build_gradio_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=8080,
        share=False,
        favicon_path="favicon.ico" if os.path.exists("favicon.ico") else None
    )
