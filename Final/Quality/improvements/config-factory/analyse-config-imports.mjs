/** Extract concrete-tool import evidence without changing Gemini CLI source. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';

const [checkout, graphFile, output] = process.argv.slice(2);
if (!checkout || !graphFile || !output) throw new Error('Usage: node analyse-config-imports.mjs CHECKOUT COUPLING_JSON OUTPUT_JSON');
const require = createRequire(path.resolve(checkout, 'package.json'));
const ts = require('typescript');
const filename = 'packages/core/src/config/config.ts';
const baseline = '4a0749aceac5643e6f85a36d7420314d85e13b52';
const source = fs.readFileSync(path.join(checkout, filename), 'utf8');
const original = execFileSync('rtk', ['proxy', 'git', '-C', checkout, 'show', `${baseline}:${filename}`], {encoding:'utf8'});
if (source !== original) throw new Error('Config source differs from report baseline');
const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true);
const graph = JSON.parse(fs.readFileSync(graphFile, 'utf8'));
const module = graph.modules.find(m => m.source === filename);
if (!module) throw new Error('Config missing from dependency-cruiser graph');
const imports = [];
for (const statement of tree.statements) {
  if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) continue;
  const bindings = statement.importClause?.namedBindings;
  if (!bindings || !ts.isNamedImports(bindings)) continue;
  const names = bindings.elements.map(e => e.name.text);
  const specifier = statement.moduleSpecifier.text;
  const concrete = names.filter(name => name.endsWith('Tool'));
  if (!concrete.length || specifier === '../tools/tools.js') continue;
  const dependency = module.dependencies.find(d => d.module === specifier);
  if (!dependency) throw new Error(`Import absent from saved graph: ${specifier}`);
  imports.push({
    module: specifier, resolved: dependency.resolved, concrete_classes: concrete,
    import_line: tree.getLineAndCharacterOfPosition(statement.getStart(tree)).line + 1,
    move_construction_to: 'proposed packages/core/src/tools/builtin-tool-assembly.ts',
    remove_direct_config_module_edge: !names.includes('resolveRipgrepPath'),
    remaining_symbols_in_config: names.includes('resolveRipgrepPath') ? ['resolveRipgrepPath'] : [],
  });
}
const removed = imports.filter(i => i.remove_direct_config_module_edge).length;
const result = {
  status: 'Design proposal only; not implemented or remeasured', baseline_commit: baseline,
  source_file: filename, source_sha256: crypto.createHash('sha256').update(source).digest('hex'),
  dependency_cruiser_version: '18.6.0', original_direct_edges: module.dependencies.length,
  concrete_tool_modules: imports.length, movable_concrete_classes: imports.reduce((n,i)=>n+i.concrete_classes.length,0),
  eligible_direct_edges_to_move: removed, imports,
  additional_required_change: 'Move ActivateSkillTool replacement/removal from initial skill discovery and reloadSkills into assembly helpers, retaining the existing caller conditions.',
  retained_dependencies: ['ToolRegistry type/API', 'resolveRipgrepPath from ripGrep.js for getRipgrepPath caching', 'memoryTool.js filename functions', 'tools.js types'],
  conditional_edge_estimate: {expression: `${module.dependencies.length} - ${removed} + 1`, value: module.dependencies.length-removed+1,
    meaning:'If these imports move and only one new assembly import is added, Config has this many direct module edges. This is an import-accounting estimate, not a dependency-cruiser after-measurement or a reduction in whole-system coupling.'},
};
fs.mkdirSync(path.dirname(output), {recursive:true});
fs.writeFileSync(output, JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({modules:imports.length, classes:result.movable_concrete_classes, removableEdges:removed, estimate:result.conditional_edge_estimate},null,2));
