[← Главная](../README.md)

# Официальные источники

| Компонент | Источник |
|---|---|
| Radmir и официальный лаунчер | [radmir.online](https://radmir.online/) |
| Faugus | [Исходный код](https://github.com/Faugus/faugus-launcher) · [Flathub](https://flathub.org/apps/io.github.Faugus.faugus-launcher) |
| GE-Proton | [Официальные выпуски](https://github.com/GloriousEggroll/proton-ge-custom/releases) |
| UMU | [Основной проект](https://github.com/Open-Wine-Components/umu-launcher) · [Сборки Faugus](https://github.com/Faugus/umu-launcher/releases) |
| Winetricks | [Проект и поддерживаемые компоненты](https://github.com/Winetricks/winetricks) |
| Flatpak / Flathub | [Подготовка системы](https://flathub.org/setup) · [Документация](https://docs.flatpak.org/en/latest/) |
| Noto Emoji | [Официальный исходник](https://github.com/googlefonts/noto-emoji) |
| DejaVu | [Официальный проект](https://dejavu-fonts.github.io/) |
| MangoHud | [Проект и настройки](https://github.com/flightlessmango/MangoHud) |

Источник ленты лаунчера подтверждён файлом `resources/app-update.yml` установленного официального приложения: `https://dl.hasslecdn.com/launcher/hassle/`. Используется также соответствующий официальный резервный адрес `dl-ru.hasslecdn.com` из исходной настройки. Текущий EXE и SHA-512 определяются по `latest.yml`, без закрепления версии лаунчера в инструкции.

Компоненты среды закреплены и проверяются по `configs/downloads.json`. Microsoft-библиотеки загружаются средствами Winetricks. Сторонние игровые зеркала и отключение TLS/контрольных сумм не используются.
