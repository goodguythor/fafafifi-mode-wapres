def calculator_tool(mcp):
    @mcp.tool()
    def add_numbers(a: float, b: float) -> float:
        """Calculate the addition of two numbers."""
        return a+b
    
    @mcp.tool()
    def multiply_numbers(a: float, b: float) -> float:
        """Calculate the multiplication of two numbers."""
        return a*b

    @mcp.tool()
    def sub_numbers(a: float, b: float) -> float:
        """Calculate the subtraction of a by b"""
        return a-b

    @mcp.tool()
    def div_numbers(a: float, b: float) -> float:
        """Calculate the division of number a by b."""
        if b == 0:
            return "Error: Division by zero"
        return a/b
