#!/usr/bin/env python3

import os
import sys
import json
from munch import Munch
import re
from ortools.algorithms import pywrapknapsack_solver

if not os.path.exists('logs/behave-zotero-1-master.json') or not os.path.exists('logs/behave-zotero-2-master.json'):
  print('not found: logs/behave-zotero-{1,2}-master.json')
  sys.exit(0)

class RunningAverage():
  def __init__(self, average=None, n=0):
    self.average = average
    self.n = n

  def __call__(self, new_value):
    self.n += 1
    if self.n == 1:
      self.average = new_value
    else:
      # https://math.stackexchange.com/questions/106700/incremental-averageing
      self.average = self.average + ((new_value - self.average) / self.n)

  def __float__(self):
    return self.average

  def __repr__(self):
    return "average: " + str(self.average)

class NoTestError(Exception):
  pass
class FailedError(Exception):
  pass

class Log:
  def __init__(self):
    self.tests = []

  def load(self, timings):
    tests = {}

    for feature in timings:
      if not 'elements' in feature: continue

      for test in feature.elements:
        if test.type == 'background': continue

        if test.status == 'failed':
          status = test.status
        elif not 'use.with_slow=true' in test.tags and not 'slow' in test.tags:
          status = 'fast'
        else:
          status = 'slow'

        # for retries, the last successful iteration (if any) will overwrite the failed iterations
        tests[re.sub(r' -- @[0-9]+\.[0-9]+ ', '', test.name)] = Munch(
          duration=sum([step.result.duration * 1000 for step in test.steps if 'result' in step and 'duration' in step.result]), # msecs
          status=status
        )
    if len(tests) == 0: raise NoTestError()
    if any(1 for test in tests.values() if test.status == 'failed'): raise FailedError()

    for name, test in tests.items():
      self.tests.append(Munch(test=name, msecs=test.duration, status=status))

log = Log()
try:
  with open('logs/behave-zotero-1-master.json') as left, open('logs/behave-zotero-2-master.json') as right:
    log.load(json.load(left, object_hook=Munch.fromDict))
    log.load(json.load(right, object_hook=Munch.fromDict))
    print(len(log.tests), 'tests')
  with open('test/balance.json') as f:
    history = json.load(f, object_hook=Munch.fromDict)

  balance = {}
  balance['tests'] = { test.test: { 'msecs': test.msecs, 'n': 1 } for test in log.tests }

  for name, test in balance['tests'].items():
    if name in history['tests']:
      h = history['tests'][name]
      avg = RunningAverage(h['msecs'], h['n'])
      avg(test['msecs'])
      balance['tests'][name] = { 'msecs': float(avg), 'n': h['n'] + 1 }

  for status in ['slow', 'fast']:
    tests = [test for test in log.tests if status in [ 'slow', test.status] ]
    print(status, len(tests))
    if status == 'slow':
      solver = pywrapknapsack_solver.KnapsackSolver.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER
    else:
      solver = pywrapknapsack_solver.KnapsackSolver.KNAPSACK_MULTIDIMENSION_CBC_MIP_SOLVER
    durations = [test.msecs for test in tests]

    solver = pywrapknapsack_solver.KnapsackSolver(solver, 'TestBalancer')
    solver.Init([1 for n in durations], [durations], [int(sum(durations)/2)])
    solver.Solve()

    balance[status] = {}
    for i in [1, 2]:
      balance[status][i] = [ test.test for t, test in enumerate(tests) if solver.BestSolutionContains(t) == (i == 1) ]
except FileNotFoundError:
  print('logs incomplete')
  sys.exit()
except NoTestError:
  print('missing tests')
  sys.exit()
except FailedError:
  print('some tests failed')
  sys.exit()

with open('test/balance.json', 'w') as f:
  json.dump(balance, f, indent='  ', sort_keys=True)