#!/bin/sh
set -eu

task_youtube_file=${1:-${HAPIC_YOUTUBE_CLIENT_JSON:-}}
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'Instala e inicia Docker antes de ejecutar Hapic con contenedores.' >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    printf '%s\n' 'El motor Docker no responde. Inícialo y vuelve a ejecutar este script.' >&2
    exit 1
fi
export HAPIC_HOST_DATA_DIR=${HAPIC_HOST_DATA_DIR:-$task_root/.hapic}
mkdir -p "$HAPIC_HOST_DATA_DIR"
if [ -n "$task_youtube_file" ]; then
    case "$task_youtube_file" in
        /*) ;;
        *) printf '%s\n' 'Indica una ruta absoluta para el JSON OAuth de Google.' >&2; exit 1 ;;
    esac
    if [ ! -f "$task_youtube_file" ]; then
        printf '%s\n' 'No se encuentra el JSON OAuth de Google indicado.' >&2
        exit 1
    fi
    export HAPIC_YOUTUBE_CLIENT_JSON=$task_youtube_file
    docker compose -f compose.yaml -f compose.youtube.yaml up --build -d
else
    docker compose up --build -d
fi
printf '%s\n' 'Hapic: http://127.0.0.1:8000'
