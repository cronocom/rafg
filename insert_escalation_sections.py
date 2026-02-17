#!/usr/bin/env python3
"""
Insert escalation analysis sections into RAGF_v2_3.tex
"""

import re

# Read the main paper
with open('papers/RAGF_v2_3.tex', 'r') as f:
    paper_content = f.read()

# Read the sections to insert
with open('papers/ESCALATION_ANALYSIS_SECTIONS.tex', 'r') as f:
    escalation_sections = f.read()

# Extract only the subsections (not the bibliography entries or notes)
# We want everything up to the "REFERENCIAS ADICIONALES" comment
escalation_text = escalation_sections.split('% =============================================================================\n% REFERENCIAS ADICIONALES')[0]

# Find the insertion point (before "State Complexity and Consistency")
marker = '\\subsubsection{State Complexity and Consistency}'

if marker in paper_content:
    # Simple string replacement (safer than regex for LaTeX)
    paper_content = paper_content.replace(
        marker,
        escalation_text + '\n' + marker,
        1  # Replace only first occurrence
    )
    
    print("✅ Inserted escalation analysis sections before 'State Complexity and Consistency'")
else:
    print("⚠️  Could not find 'State Complexity and Consistency' marker")
    print("   Searching for alternative markers...")
    
    # Try alternative markers
    if '\\subsection{Operational Sustainability}' in paper_content:
        marker = '\\subsection{Operational Sustainability}'
        paper_content = paper_content.replace(
            marker,
            escalation_text + '\n' + marker,
            1
        )
        print("✅ Inserted before 'Operational Sustainability' instead")
    else:
        print("❌ Could not find insertion point. Please insert manually.")
        print("\nSearch for one of these markers in papers/RAGF_v2_3.tex:")
        print("  - \\subsubsection{State Complexity and Consistency}")
        print("  - \\subsection{Operational Sustainability}")
        print("\nThen insert the content from papers/ESCALATION_ANALYSIS_SECTIONS.tex BEFORE that marker.")
        exit(1)

# Add bibliography entries
bib_entries = """
\\bibitem{faa-human-factors}
Federal Aviation Administration.
\\newblock Human Factors Design Guide.
\\newblock FAA AC 60-22, 2023.

\\bibitem{kahneman2009conditions}
Daniel Kahneman and Gary Klein.
\\newblock Conditions for intuitive expertise: a failure to disagree.
\\newblock {\\em American Psychologist}, 64(6):515--527, 2009.
"""

# Insert bibliography entries before \end{thebibliography}
bib_end_marker = '\\end{thebibliography}'
if bib_end_marker in paper_content:
    paper_content = paper_content.replace(
        bib_end_marker,
        bib_entries + '\n' + bib_end_marker,
        1
    )
    print("✅ Added bibliography entries (faa-human-factors, kahneman2009conditions)")
else:
    print("⚠️  Could not find bibliography section")

# Write updated paper
with open('papers/RAGF_v2_3.tex', 'w') as f:
    f.write(paper_content)

print("\n✨ Paper updated successfully!")
print("\nNext steps:")
print("  1. Review changes: git diff papers/RAGF_v2_3.tex")
print("  2. Upload to Overleaf (or install LaTeX locally)")
print("  3. Compile PDF online at Overleaf")
print("  4. Download PDF and commit: git add papers/RAGF_v2_3.* && git commit")
print("\n📝 To install LaTeX on Mac:")
print("  brew install --cask mactex")
print("  (Warning: ~4GB download)")
