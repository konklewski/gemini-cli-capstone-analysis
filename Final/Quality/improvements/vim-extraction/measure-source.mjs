/**
 * Measure physical source spans with the checkout's locked TypeScript parser.
 * These spans include comments and blank lines inside each function. They are
 * not SciTools Understand's CountLineCode or Cyclomatic metrics.
 *
 * Usage: node measure-source.mjs CHECKOUT OUTPUT_JSON
 */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const [checkoutArgument, outputArgument] = process.argv.slice(2);
if (!checkoutArgument || !outputArgument) {
  throw new Error('Usage: node measure-source.mjs CHECKOUT OUTPUT_JSON');
}

const checkout = resolve(checkoutArgument);
const checkoutRequire = createRequire(resolve(checkout, 'package.json'));
const ts = checkoutRequire('typescript');
const relativePath = 'packages/cli/src/ui/components/shared/vim-buffer-actions.ts';
const source = readFileSync(resolve(checkout, relativePath), 'utf8');
const sourceFile = ts.createSourceFile(
  relativePath,
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TS,
);
if (sourceFile.parseDiagnostics.length) {
  throw new Error('TypeScript parser reported a source error.');
}

const functions = sourceFile.statements
  .filter(ts.isFunctionDeclaration)
  .map((declaration) => {
    const startLine = sourceFile.getLineAndCharacterOfPosition(
      declaration.getStart(sourceFile),
    ).line + 1;
    const endLine = sourceFile.getLineAndCharacterOfPosition(
      declaration.getEnd() - 1,
    ).line + 1;
    return {
      name: declaration.name?.text ?? '(anonymous)',
      start_line: startLine,
      end_line: endLine,
      physical_line_span: endLine - startLine + 1,
    };
  });

const result = {
  definition: 'Inclusive physical function span, excluding preceding JSDoc but including internal blank/comment lines. Not Understand CountLineCode or Cyclomatic.',
  typescript_version: ts.version,
  source_path: relativePath,
  source_sha256: createHash('sha256').update(source).digest('hex'),
  functions,
  maximum_physical_function_span: Math.max(...functions.map((item) => item.physical_line_span)),
};
writeFileSync(resolve(outputArgument), `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
