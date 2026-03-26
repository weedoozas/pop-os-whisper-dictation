# Pop!_OS Whisper Dictation

Dictado local para `Pop!_OS`, `COSMIC` y `Wayland`.

Este proyecto nacio para escribir rapido en chat usando una combinacion simple de teclado, transcripcion local con Whisper y correccion ortografica posterior. El flujo actual usa `faster-whisper` con el modelo `medium` y una capa de correccion con `LanguageTool`.

## Que hace

- `Super+Shift+Enter` una vez: reproduce un sonido y empieza a grabar.
- `Super+Shift+Enter` otra vez: detiene la grabacion, transcribe el audio, corrige el texto, lo copia al portapapeles y trata de escribirlo en la ventana enfocada.
- Si el pegado automatico falla, el texto igual queda guardado en el portapapeles.

## Stack

- `faster-whisper`
- `Whisper medium`
- `LanguageTool`
- `arecord`
- `wl-clipboard`
- `wtype`
- `notify-send`

## Pensado para Pop!_OS

Este proyecto esta orientado a:

- `Pop!_OS`
- `COSMIC`
- `Wayland`

Usa herramientas nativas de Wayland para evitar hacks de X11.

## Como funciona

1. Se graba audio con `arecord`.
2. Se transcribe localmente con `faster-whisper`.
3. Whisper detecta el idioma principal del audio.
4. Se corrige el texto con `LanguageTool` usando el idioma detectado.
5. El resultado se copia al portapapeles con `wl-copy`.
6. Se intenta escribir el texto con `wtype` en la app enfocada.

## Limitaciones actuales

- La mezcla de espanol e ingles en una misma frase puede funcionar, pero el sistema sigue eligiendo un idioma principal por mensaje.
- El modelo `medium` mejora bastante la calidad, pero introduce mas latencia que `small`.
- `LanguageTool` puede arreglar ortografia y gramatica, pero a veces tambien hace correcciones raras.

## Instalacion rapida

Instala dependencias del sistema:

```bash
sudo apt update
sudo apt install -y wl-clipboard wtype python3-pip python3-venv default-jre-headless libnotify-bin
```

Crea el entorno e instala dependencias Python:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install faster-whisper language-tool-python
```

## Uso

Ejecuta el script principal con:

```bash
./run-voice-toggle.sh
```

La primera ejecucion real descargara caches necesarias de Whisper y LanguageTool.

## Atajo en COSMIC

El proyecto usa un shortcut nativo de COSMIC. Si necesitas configurarlo manualmente, crea o ajusta:

`~/.config/cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom`

Con una entrada como esta:

```ron
{
    (modifiers: [Super, Shift], key: "Return", description: Some("Voice Toggle")): Spawn("/ruta/al/proyecto/run-voice-toggle.sh"),
}
```

## Archivos principales

- `voice_toggle.py` - logica principal del toggle, transcripcion y correccion
- `run-voice-toggle.sh` - lanzador simple para COSMIC
- `performance.log` - log local de tiempos y resultados

## Rendimiento

El script registra:

- duracion de grabacion
- tiempo de transcripcion
- tiempo de correccion
- idioma detectado
- si el texto se corrigio o no

Esto ayuda a decidir si `medium` vale la pena segun tu maquina.

## Licencia

MIT
