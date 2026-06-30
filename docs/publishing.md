# Publishing the SDKs

Lians ships five SDKs. This is the release process and the registry path for each.
Releases are cut by pushing a semver tag; `release.yml` builds the language
artifacts and attaches them to the GitHub Release.

```bash
git tag v0.2.1
git push origin v0.2.1
```

| SDK | Registry | How it's published | Secret(s) needed |
|-----|----------|--------------------|------------------|
| **Python** | [PyPI](https://pypi.org/project/lians-sdk) | `publish-lian.yml` builds sdist+wheel and uploads via `twine` | `PYPI_API_TOKEN` |
| **TypeScript** | [npm](https://www.npmjs.com/package/@lians-ai/lians) | `publish-lian-npm.yml` runs `npm publish` | `NPM_TOKEN` |
| **Go** | proxy.golang.org / pkg.go.dev | `release.yml` → `go-tag` auto-mirrors the tag to the module path (see below) | none |
| **Java** | Maven Central (gated) / GitHub Release jar | `release.yml` → `maven-central` (`mvn deploy -P release`) when opted in; else jar on the Release | `OSSRH_USERNAME`, `OSSRH_PASSWORD`, `MAVEN_GPG_KEY`, `MAVEN_GPG_PASSPHRASE` + var `PUBLISH_MAVEN_CENTRAL=true` |
| **C** | source tarball on the GitHub Release | packaged by `release.yml` (vendored into the consumer build) | none |

## Go module tags (automatic)

The Go module lives in a subdirectory, so `go get` resolves a version from a tag
**prefixed with the module path**. The `go-tag` job in `release.yml` creates this
automatically when you push a `vX.Y.Z` tag — no manual step:

```
v0.3.0  ──(release.yml go-tag)──▶  agentmem/sdk/go/v0.3.0
```

Consumers then use:

```bash
go get github.com/Lians-ai/Lians/agentmem/sdk/go@v0.3.0
```

## Java → Maven Central

Out of the box, `release.yml` attaches the built jar to the GitHub Release (no
secrets). To publish to **Maven Central**: add the `OSSRH_*` / `MAVEN_GPG_*`
secrets, set the repository **variable** `PUBLISH_MAVEN_CENTRAL=true`, and the
`maven-central` job runs `mvn -B deploy -P release` — the `release` profile in
`pom.xml` builds sources + javadoc, GPG-signs, and publishes via the Sonatype
Central Portal. (GitHub Packages is an alternative: point `distributionManagement`
at `https://maven.pkg.github.com/Lians-ai/Lians` and use `GITHUB_TOKEN`.)

## C

The C SDK is distributed as source (header + `.c` files) — the idiomatic model for
a small libcurl client. `release.yml` packages `agentmem/sdk/c` into
`lians-c-<version>.tar.gz` on the Release; consumers vendor it and build with
their own CMake/Make. (A future option: an apt/conan/vcpkg recipe.)
