#!/bin/sh

sudo chsh -s "$(which zsh)" "$USER"

mv .zshrc .zshrc.bak

curl https://raw.githubusercontent.com/lordmathis/dotfiles/main/install.sh | zsh -s -- common
