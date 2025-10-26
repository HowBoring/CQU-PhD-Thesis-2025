# vim: set ft=perl:
$out_dir = 'build';
$do_cd = 1;
$pdflatex = 'xelatex -quiet -halt-on-error -interaction=nonstopmode synctex=1 %O %S';
$xelatex = "xelatex -shell-escape -file-line-error -halt-on-error -interaction=nonstopmode -synctex=1 %O %S";
$pdf_mode = 5;
$postscript_mode = $dvi_mode = 0;
$clean_ext = '.aux .bbl equ glo gls hd idx ilg ind lof lot out blg log thm toc synctex.gz lofEN lotEN equEN';
$makeindex = 'makeindex -s gind.ist %O -o %D %S';
add_cus_dep('glo', 'gls', 0, 'makeglo2gls');
sub makeglo2gls {
    system("makeindex -s gglo.ist -o \"$_[0].gls\" \"$_[0].glo\"");
}

$max_repeat = 5;   # 最大循环次数
$force_mode = 1;   # 等价于命令行 -f
$allow_continue = 1;

$cleanup_includes_cusdep_generated = 1;
$postscript_mode = 0;

$cleanup_includes_cusdep_generated = 1;

# 关键部分：即使达到最大次数，也不报错
$latexmk_exit_code = 0;# 允许的最大重复次数（例如 10）
