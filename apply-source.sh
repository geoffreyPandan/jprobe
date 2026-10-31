#!/usr/bin/env bash
set -euo pipefail

if (( $# != 1 )); then
  echo "Usage: $0 /path/to/upstream-checkout" >&2
  exit 2
fi

checkout=$(realpath "$1")
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
projects=(root frida-core frida-gum frida-python frida-tools idun)
commits=(
  f74818ada177756bd95c26235cdd26ebe4f07e76
  f91556129517937e82831458d10f6b8f4ca06dbb
  5ebe3aeccab8dcd4b727378dab67fb15fa8a3cca
  c6862934002a1835c51cd6a7ca4d7b949c968971
  a8c12cef7f728812bc8c70197505e8f40e1c26e4
  eaf98270beab0ecf174e611d99036db6843a1865
)

project_dir() {
  if [[ $1 == root ]]; then
    printf '%s\n' "$checkout"
  else
    printf '%s\n' "$checkout/subprojects/$1"
  fi
}

for i in "${!projects[@]}"; do
  project=${projects[$i]}
  target=$(project_dir "$project")
  actual=$(git -C "$target" rev-parse HEAD)
  if [[ $actual != "${commits[$i]}" ]]; then
    echo "$project is at $actual; expected ${commits[$i]}" >&2
    exit 1
  fi
  git -C "$target" apply --check "$kit/patches/$project.patch"
  if [[ -d $kit/new-source/$project ]]; then
    while IFS= read -r -d '' source; do
      relative=${source#"$kit/new-source/$project/"}
      destination=$target/$relative
      if [[ -e $destination ]] && ! cmp -s "$source" "$destination"; then
        echo "Refusing to overwrite $destination" >&2
        exit 1
      fi
    done < <(find "$kit/new-source/$project" -type f -print0)
  fi
done

for project in "${projects[@]}"; do
  target=$(project_dir "$project")
  git -C "$target" apply "$kit/patches/$project.patch"
  if [[ -d $kit/new-source/$project ]]; then
    cp -a "$kit/new-source/$project/." "$target/"
  fi
done

echo "Applied jprobe source changes to $checkout"
