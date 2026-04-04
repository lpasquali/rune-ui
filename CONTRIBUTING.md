# Contributing to rune-ui

First off, thank you for considering contributing to rune-ui! It's people like you that make rune-ui such a great tool.

## Where do I go from here?

If you've noticed a bug or have a feature request, make one! It's generally best if you get confirmation of your bug or approval for your feature request this way before starting to code.

## "Zero NPM" Policy

RUNE UI adheres to a strict "Zero NPM" policy to eliminate supply chain risks. All interactive features must be implemented using:
- **Python 3.12+ (FastAPI)**
- **HTMX** for dynamic content
- **Jinja2** for server-side templates
- **Vanilla CSS** for styling

## Pull Request Guidelines

1. **Quality Gates:** Your PR must pass all RuneGate quality checks, including a minimum of **97% coverage**.
2. **Commit Style:** Use descriptive commit messages following the Conventional Commits specification.
3. **Issue Linking:** Always link your PR to a corresponding GitHub Issue.

## Release Process

RUNE follows a synchronized release process across all its repositories. For details on how releases are triggered, built, and published, please refer to the [RUNE Release Documentation](https://github.com/lpasquali/rune-docs/blob/main/docs/releasing.md).

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct. By participating in this project you agree to abide by its terms. See `CODE_OF_CONDUCT.md` for more information.
