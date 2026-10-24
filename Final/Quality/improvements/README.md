# Quality improvements

Evidence for the final report, based on Gemini CLI `v0.64.0` (`4a0749a`).

- [Vim extraction](vim-extraction/REPRODUCING.txt): the implemented change, tests, measurements and reproduction steps.
- [Config factory](config-factory/design-evidence.txt): the proposed tool-assembly split and component diagram.
- [Security](security/security-evidence.txt): audit results and proposed dependency updates.

Only the Vim change was implemented. Both diagrams have PlantUML source, SVG and PNG versions.

To render them, use [PlantUML 1.2026.9](https://github.com/plantuml/plantuml/releases/tag/v1.2026.9) and Java:

```sh
java -jar /path/to/plantuml-1.2026.9.jar -tsvg vim-extraction/vim-change-movement.puml config-factory/config-tool-assembly-proposal.puml
java -jar /path/to/plantuml-1.2026.9.jar -tpng vim-extraction/vim-change-movement.puml config-factory/config-tool-assembly-proposal.puml
```

JAR SHA-256: `aa4a1d06f8911c4b842beff4828dd955be431692b631a312d04c0e9fab9581de`.

Keep raw exports unchanged. After updating supporting files, run `python create_delivery_manifest.py .` from this folder to refresh their hashes.
