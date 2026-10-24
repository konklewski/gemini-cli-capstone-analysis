/**
 * Check that the extraction preserves the original TypeScript statements.
 * This structural check complements, rather than replaces, behavioral tests.
 * Usage: node verify-extraction.mjs CHECKOUT OUTPUT_JSON
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const [checkoutArgument, outputArgument] = process.argv.slice(2);
if (!checkoutArgument || !outputArgument) {
  throw new Error('Usage: node verify-extraction.mjs CHECKOUT OUTPUT_JSON');
}
const checkout = resolve(checkoutArgument);
const checkoutRequire = createRequire(resolve(checkout, 'package.json'));
const ts = checkoutRequire('typescript');
const baseline = '4a0749aceac5643e6f85a36d7420314d85e13b52';
const relativePath = 'packages/cli/src/ui/components/shared/vim-buffer-actions.ts';
const originalText = execFileSync('git', ['show', `${baseline}:${relativePath}`], {
  cwd: checkout,
  encoding: 'utf8',
});
const changedText = readFileSync(resolve(checkout, relativePath), 'utf8');
const parse = (text) => ts.createSourceFile(relativePath, text, ts.ScriptTarget.Latest, true);
const before = parse(originalText);
const after = parse(changedText);
const printer = ts.createPrinter({ removeComments: true });
const print = (node, file) => printer.printNode(ts.EmitHint.Unspecified, node, file);
const functions = (file) => file.statements.filter(ts.isFunctionDeclaration);
const findFunction = (file, name) => functions(file).find((node) => node.name?.text === name);
const beforeHandler = findFunction(before, 'handleVimAction');
const afterHandler = findFunction(after, 'handleVimAction');
const helper = findFunction(after, 'handleVimChangeMovement');
assert(beforeHandler && afterHandler && helper, 'Expected handler/helper missing');
const beforeSwitch = beforeHandler.body.statements.find(ts.isSwitchStatement);
const afterSwitch = afterHandler.body.statements.find(ts.isSwitchStatement);
assert(beforeSwitch && afterSwitch, 'Expected outer switch missing');
const oldClauses = beforeSwitch.caseBlock.clauses;
const newClauses = afterSwitch.caseBlock.clauses;
assert.equal(oldClauses.length, newClauses.length, 'Action cases changed');
let checkedClauses = 0;
let checkedMovement = false;
for (let index = 0; index < oldClauses.length; index++) {
  const oldClause = oldClauses[index];
  const newClause = newClauses[index];
  if (ts.isCaseClause(oldClause) && oldClause.expression.text === 'vim_change_movement') {
    assert(ts.isBlock(oldClause.statements[0]));
    const originalStatements = oldClause.statements[0].statements;
    assert.equal(helper.body.statements.length, originalStatements.length + 1);
    assert.equal(print(helper.body.statements[0], after), print(beforeHandler.body.statements[0], before));
    originalStatements.forEach((statement, statementIndex) => {
      assert.equal(print(statement, before), print(helper.body.statements[statementIndex + 1], after));
    });
    assert.equal(newClause.statements.length, 1);
    assert.equal(print(newClause.statements[0], after), 'return handleVimChangeMovement(state, action);');
    checkedMovement = true;
  } else {
    assert.equal(print(oldClause, before), print(newClause, after));
    checkedClauses++;
  }
}
assert(checkedMovement, 'Movement branch was not checked');
const imports = (file) => file.statements.filter(ts.isImportDeclaration).map((node) => print(node, file));
assert.deepEqual(imports(before), imports(after), 'Imports changed');
functions(before).filter((node) => node.name?.text !== 'handleVimAction').forEach((node) => {
  assert.equal(print(node, before), print(findFunction(after, node.name.text), after));
});
const bufferPath = 'packages/cli/src/ui/components/shared/text-buffer.ts';
assert.equal(readFileSync(resolve(checkout, bufferPath), 'utf8'), execFileSync('git', ['show', `${baseline}:${bufferPath}`], { cwd: checkout, encoding: 'utf8' }));
const result = {
  baseline_commit: baseline,
  typescript_version: ts.version,
  unchanged_outer_case_clauses: checkedClauses,
  extracted_statements_identical_after_normalizing_formatting_and_comments: true,
  delegation_verified: true,
  imports_unchanged: true,
  existing_private_helpers_unchanged: true,
  text_buffer_module_unchanged: true,
  limitation: 'Structural equality does not replace tests or prove correctness for all possible inputs. Existing import cycle is unchanged.',
};
writeFileSync(resolve(outputArgument), `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
