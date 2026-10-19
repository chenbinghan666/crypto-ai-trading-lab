"""Offline phase-1 validation; no imports from trading engines or network calls."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    required = [
        'README.md', '.gitignore', '.env.example', 'pyproject.toml',
        'docs/ARCHITECTURE.md', 'docs/INSTALL_WINDOWS.md', 'docs/DECISIONS.md',
        'docs/PHASE_PLAN.md', 'docs/TRADING_FREQUENCY_POLICY.md',
        'docs/CLOUD_DEPLOYMENT_PLAN.md', 'reports/ENVIRONMENT_AUDIT.md',
        'docs/UPSTREAM_REVIEW.md', 'reports/evidence/index.json',
    ]
    errors = ['Missing: ' + name for name in required if not (ROOT / name).is_file()]
    try:
        p = json.loads((ROOT / 'configs/paper/policy.json').read_text(encoding='utf-8'))
        expected = {'phase': 1, 'live_enabled': False, 'dry_run': True,
                    'execution_enabled': False, 'api_enabled': False,
                    'allow_short': False, 'market_type': 'spot', 'leverage': 1,
                    'agent_mode': 'agent_required', 'api_monthly_budget_cny': 30,
                    'daily_trade_target': None}
        for key, value in expected.items():
            if type(p.get(key)) is not type(value) or p.get(key) != value:
                errors.append('Unsafe scaffold setting: ' + key)
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    if errors:
        print('\n'.join(errors))
        return 1
    print('PASS: phase-1 files and conservative defaults. Runtime NOT implemented or tested.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
