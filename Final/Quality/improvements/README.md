# Quality improvements

Supporting files for the final report, based on Gemini CLI `v0.64.0` (`4a0749a`).

- [vim-extraction](vim-extraction/REPRODUCING.txt): the implemented change, exact before/after revisions, patches, tests and Understand exports. `vim-change-movement.svg` is the diagram for the report.
- [config-factory](config-factory/design-evidence.txt): the proposed tool-assembly split, source inventory and component diagram. This proposal was not implemented.
- [security](security/security-evidence.txt): the dated npm audit exports, two dependency examples and proposed fixes. No dependency update was applied.

The Vim handler's cyclomatic complexity changed from 196 to 188. The extracted helper measures 9, so the combined decision count, `sum(Cyclomatic - 1)`, remains 195. Both controlled versions were measured with Understand Build 1265. The original group measurement used Build 1264 and gave the same baseline function values.

Raw CSVs, diagnostics, audit outputs and test reports are kept alongside derived summaries. See the Vim reproduction instructions for commands and limitations. `delivery-manifest.json` records the retained files and their SHA-256 hashes; regenerate it with `python create_delivery_manifest.py .` from this folder.

Both diagrams include PlantUML source, SVG and PNG. Render with PlantUML 1.2026.9 (Java required):

```sh
java -jar /path/to/plantuml-1.2026.9.jar -tsvg vim-extraction/vim-change-movement.puml config-factory/config-tool-assembly-proposal.puml
java -jar /path/to/plantuml-1.2026.9.jar -tpng vim-extraction/vim-change-movement.puml config-factory/config-tool-assembly-proposal.puml
```

Renderer: [PlantUML 1.2026.9](https://github.com/plantuml/plantuml/releases/tag/v1.2026.9). JAR SHA-256: `aa4a1d06f8911c4b842beff4828dd955be431692b631a312d04c0e9fab9581de`.
