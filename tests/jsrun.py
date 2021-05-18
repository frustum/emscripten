# Copyright 2013 The Emscripten Authors.  All rights reserved.
# Emscripten is available under two separate licenses, the MIT license and the
# University of Illinois/NCSA Open Source License.  Both these licenses can be
# found in the LICENSE file.

import logging
import os
import sys
from subprocess import Popen, PIPE, CalledProcessError

from tools import shared

WORKING_ENGINES = {} # Holds all configured engines and whether they work: maps path -> True/False

# Special value for passing to assert_returncode which means we expect that program
# to fail with non-zero return code, but we don't care about specifically which one.
NON_ZERO = -1


def make_command(filename, engine, args=[]):
  # if no engine is needed, indicated by None, then there is a native executable
  # provided which we can just run
  if engine[0] is None:
    executable = shared.unsuffixed(os.path.abspath(filename)) + '.exe'
    return [executable] + args
  if type(engine) is not list:
    engine = [engine]
  # Emscripten supports multiple javascript runtimes.  The default is nodejs but
  # it can also use d8 (the v8 engine shell) or jsc (JavaScript Core aka
  # Safari).  Both d8 and jsc require a '--' to delimit arguments to be passed
  # to the executed script from d8/jsc options.  Node does not require a
  # delimeter--arguments after the filename are passed to the script.
  #
  # Check only the last part of the engine path to ensure we don't accidentally
  # label a path to nodejs containing a 'd8' as spidermonkey instead.
  jsengine = os.path.basename(engine[0])
  # Use "'d8' in" because the name can vary, e.g. d8_g, d8, etc.
  is_d8 = 'd8' in jsengine or 'v8' in jsengine
  is_jsc = 'jsc' in jsengine
  is_wasmer = 'wasmer' in jsengine
  is_wasmtime = 'wasmtime' in jsengine
  # Disable true async compilation (async apis will in fact be synchronous) for now
  # due to https://bugs.chromium.org/p/v8/issues/detail?id=6263
  shell_option_flags = ['--no-wasm-async-compilation'] if is_d8 else []
  command_flags = []
  if is_wasmer:
    command_flags += ['run']
  if is_wasmer or is_wasmtime:
    # in a wasm runtime, run the wasm, not the js
    filename = shared.unsuffixed(filename) + '.wasm'
  # Separates engine flags from script flags
  flag_separator = ['--'] if is_d8 or is_jsc else []
  return engine + command_flags + [filename] + shell_option_flags + flag_separator + args


def check_engine(engine):
  if type(engine) is list:
    engine_path = engine[0]
  else:
    engine_path = engine
  global WORKING_ENGINES
  if engine_path not in WORKING_ENGINES:
    logging.debug('Checking JS engine %s' % engine)
    try:
      output = run_js(shared.path_from_root('tests/hello_world.js'), engine, skip_check=True)
      if 'hello, world!' in output:
        WORKING_ENGINES[engine_path] = True
      else:
        WORKING_ENGINES[engine_path] = False
    except Exception as e:
      logging.info('Checking JS engine %s failed. Check your config file. Details: %s' % (str(engine), str(e)))
      WORKING_ENGINES[engine_path] = False
  return WORKING_ENGINES[engine_path]


def require_engine(engine):
  engine_path = engine[0]
  # if None is the "engine", it means we compiled to a native executable;
  # there is no engine to check here
  if engine_path is None:
    return
  if engine_path not in WORKING_ENGINES:
    check_engine(engine)
  if not WORKING_ENGINES[engine_path]:
    logging.critical('The engine (%s) does not seem to work, check the paths in the config file' % engine)
    sys.exit(1)


def run_js(filename, engine, args=[],
           stdin=None, stdout=PIPE, stderr=None, cwd=None,
           full_output=False, assert_returncode=0, skip_check=False):
  # We used to support True here but we no longer do.  Assert here just in case.
  assert(type(assert_returncode) == int)

  """Execute javascript code generated by tests, with possible timeout."""
  if not os.path.exists(filename):
    raise Exception('output file not found: ' + filename)

  command = make_command(filename, engine, args)
  try:
    proc = Popen(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        universal_newlines=True)
    stdout, stderr = proc.communicate()
  except Exception:
    # the failure may be because the engine is not present. show the proper
    # error in that case
    if not skip_check:
      require_engine(engine)
    # if we got here, then require_engine succeeded, so we can raise the original error
    raise

  out = ['' if o is None else o for o in (stdout, stderr)]
  ret = '\n'.join(out) if full_output else out[0]

  if assert_returncode == NON_ZERO:
    if proc.returncode == 0:
      raise CalledProcessError(proc.returncode, ' '.join(command), str(ret))
  elif proc.returncode != assert_returncode:
    raise CalledProcessError(proc.returncode, ' '.join(command), str(ret))

  return ret
