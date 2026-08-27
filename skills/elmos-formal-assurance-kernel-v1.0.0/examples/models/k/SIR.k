module SIR-SYNTAX
  syntax Exp ::= Int | Exp "+" Exp [left, strict]
endmodule

module SIR
  imports SIR-SYNTAX
  imports INT
  configuration <k> $PGM:Exp </k>
  rule <k> I1:Int + I2:Int => I1 +Int I2 ... </k>
endmodule
