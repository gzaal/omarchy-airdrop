# Maintainer: gzaal <https://github.com/gzaal>
pkgname=omarchy-airdrop-git
pkgver=0.1.0.r0.g0000000
pkgrel=1
pkgdesc="AirDrop-style local file transfer for Omarchy (LocalSend v2 compatible, optional native AirDrop)"
arch=(any)
url="https://github.com/gzaal/omarchy-airdrop"
license=(MIT)
depends=(python openssl)
optdepends=(
  'owl: AWDL daemon for native AirDrop (requires supported Wi-Fi adapter)'
  'opendrop: native AirDrop protocol client'
)
makedepends=(git)
provides=(omarchy-airdrop)
conflicts=(omarchy-airdrop)
source=("${pkgname}::git+${url}.git")
sha256sums=(SKIP)

pkgver() {
  cd "$srcdir/${pkgname}"
  git describe --long --tags 2>/dev/null | sed 's/^v//;s/\([^-]*-g\)/r\1/;s/-/./g' || echo "0.1.0.r0"
}

build() {
  cd "$srcdir/${pkgname}"
  python3 -m compileall -q airdropd
}

package() {
  cd "$srcdir/${pkgname}"
  install -Dm755 bin/airdrop "$pkgdir/usr/bin/airdrop"
  install -Dm755 ui/airdrop-share "$pkgdir/usr/bin/airdrop-share"

  local site="$pkgdir/usr/lib/python3/site-packages"
  mkdir -p "$site"
  cp -r airdropd "$site/"
  find "$site" -name '__pycache__' -type d -exec rm -rf {} +

  install -Dm644 systemd/airdropd.service "$pkgdir/usr/lib/systemd/user/airdropd.service"
  install -Dm644 systemd/airdropd-owl@.service "$pkgdir/usr/lib/systemd/system/airdropd-owl@.service"

  install -Dm644 ui/omarchy-plugin/omarchy-airdrop/manifest.json \
    "$pkgdir/usr/share/omarchy-airdrop/plugin/omarchy-airdrop/manifest.json"
  install -Dm644 ui/omarchy-plugin/omarchy-airdrop/AirDrop.qml \
    "$pkgdir/usr/share/omarchy-airdrop/plugin/omarchy-airdrop/AirDrop.qml"
  install -Dm644 ui/keybinds-reference.lua "$pkgdir/usr/share/doc/$pkgname/keybinds-reference.lua"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
