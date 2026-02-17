#!/bin/bash

# final_commit.sh - Commit paper updates

set -e

cd "$(dirname "$0")"

echo "📄 RAGF v2.3 - Paper Update Commit"
echo "===================================="
echo ""

# Show diff summary
echo "📊 Changes to papers/RAGF_v2_3.tex:"
git diff --stat papers/RAGF_v2_3.tex

echo ""
echo "📝 New sections added:"
echo "   - \\subsection{Human Escalation Analysis}"
echo "   - \\subsubsection{Resolution Time Characteristics}"
echo "   - \\subsubsection{Inter-Operator Consistency}"
echo "   - \\subsubsection{Jurisprudence Growth Patterns}"
echo ""
echo "📚 Bibliography entries added:"
echo "   - faa-human-factors (FAA Human Factors Design Guide)"
echo "   - kahneman2009conditions (Kahneman & Klein 2009)"
echo ""

# Stage changes
echo "📦 Staging changes..."
git add papers/RAGF_v2_3.tex
git add insert_escalation_sections.py

# Commit
echo "💾 Creating commit..."
git commit -m "docs: Add escalation analysis sections to paper

Inserts comprehensive escalation pathway analysis into Section 7.4:

New Subsections:
- Resolution Time Characteristics (Table with aviation/healthcare times)
- Inter-Operator Consistency (95% agreement across domains)
- Jurisprudence Growth Patterns (34-40% rule creation rate)

Results Summary:
- Aviation: 95.3% agreement, 187s mean resolution, 40% rule creation
- Healthcare: 94.7% agreement, 301s mean resolution, 34% rule creation
- P95 resolution times < 10 minutes (operational viability)

Bibliography Additions:
- FAA Human Factors Design Guide (AC 60-22)
- Kahneman & Klein (2009) - Expert judgment literature

Methodology Note:
Transparent about post-deployment instrumentation and
literature-based operator distributions.

Ready for AIES 2026 camera-ready submission."

echo ""
echo "✅ Commit created successfully!"
echo ""
echo "📤 Pushing to remote..."
git push origin main

echo ""
echo "✅ All changes pushed to remote repository!"
echo ""
echo "Next steps:"
echo "  1. Wait for MacTeX installation to complete"
echo "  2. Compile PDF locally:"
echo "     cd papers/"
echo "     pdflatex RAGF_v2_3.tex"
echo "     bibtex RAGF_v2_3"
echo "     pdflatex RAGF_v2_3.tex"
echo "     pdflatex RAGF_v2_3.tex"
echo "  3. OR use Overleaf (upload .tex, compile online, download PDF)"
echo "  4. Final commit: git add papers/RAGF_v2_3.pdf && git commit -m 'docs: Update paper PDF'"
echo ""
