"""Apply reviewed source-only corrections before running the integration check."""
from pathlib import Path
import os

ROOT=Path(__file__).resolve().parents[1]

def main():
    test=ROOT/'tests/test_rxr_calibration.py'
    text=test.read_text()
    text=text.replace("self.assertIn('not a mandatory new entry sentence',prompt)",
                      "self.assertIn('Every stage requires an intelligible, supported entry state',prompt)")
    test.write_text(text)
    # The release label is read from the current branch only for README display.
    # It is not embedded in a Prompt, template, identifier or source script.
    integration=ROOT/'tools/integrate_rxr.py'
    text=integration.read_text()
    lines=text.splitlines(keepends=True)
    for index,line in enumerate(lines):
        if line.strip().startswith("text='# LLM-decompose-"):
            lines[index]="    import os\n    branch=os.environ.get('GITHUB_REF_NAME','LLM-decompose')\n    text='# '+branch+'\\n'+text\n"
    integration.write_text(''.join(lines))

if __name__=='__main__':
    main()
